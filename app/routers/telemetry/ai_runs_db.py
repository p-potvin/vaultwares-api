"""Persistence for model-run telemetry.

Shares the telemetry pool from .db, same as ai_sessions. Runs are append-only:
ingest never updates an existing row, it only skips duplicates, so a spool file
replayed after a partial drain is a no-op rather than a double count.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .db import get_pool

_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_SQL = _ROOT / "migrations" / "telemetry" / "004_ai_runs.sql"
_schema_ready = False

# Written straight to columns; everything else on a record lands in `extra`.
_COLUMNS: Tuple[str, ...] = (
    "run_id", "parent_run_id", "provider", "runtime", "model", "model_revision",
    "quantization", "task", "host", "project", "service", "session_id", "caller",
    "environment", "queued_at", "started_at", "first_token_at", "ended_at",
    "queue_ms", "ttft_ms", "duration_ms", "tokens_per_second", "input_tokens",
    "output_tokens", "cached_input_tokens", "reasoning_tokens", "total_tokens",
    "temperature", "top_p", "max_tokens", "seed", "stream", "batch_size",
    "context_length", "status", "finish_reason", "error_class", "error_message",
    "http_status", "retries", "request_id", "served_model", "upstream_provider",
    "provider_ms", "backend", "role", "load_ms", "cost_usd", "credits_used",
    "billing_source", "budget_remaining", "is_free", "priced_exactly",
    "cost_state", "device", "gpu_name", "gpu_index", "gpu_util_pct",
    "gpu_temp_c", "gpu_power_w", "vram_used_mb", "vram_peak_mb", "vram_total_mb",
    "cpu_pct", "rss_mb", "prompt_chars", "prompt_hash", "completion_chars",
    "image_count", "audio_seconds", "video_frames", "output_bytes", "steps",
    "sampler", "scheduler", "cfg_scale", "width", "height", "lora_count",
)

_TIMESTAMPS = {"queued_at", "started_at", "first_token_at", "ended_at"}
_INTS = {
    "max_tokens", "seed", "batch_size", "context_length", "http_status", "retries",
    "gpu_index", "prompt_chars", "completion_chars", "image_count", "video_frames",
    "steps", "width", "height", "lora_count", "input_tokens", "output_tokens",
    "cached_input_tokens", "reasoning_tokens", "total_tokens", "output_bytes",
}
_FLOATS = {
    "queue_ms", "ttft_ms", "duration_ms", "tokens_per_second", "temperature",
    "top_p", "cost_usd", "credits_used", "budget_remaining", "gpu_util_pct",
    "gpu_temp_c", "gpu_power_w", "vram_used_mb", "vram_peak_mb", "vram_total_mb",
    "cpu_pct", "rss_mb", "audio_seconds", "cfg_scale", "provider_ms", "load_ms",
}
_BOOLS = {"stream", "is_free", "priced_exactly"}
_KNOWN = set(_COLUMNS) | {"tags", "extra"}


async def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))
    _schema_ready = True


def _coerce_dt(value: Any) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        text = str(value)
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _as_int(value: Any) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    # NaN/Inf would poison every downstream avg() and percentile.
    return result if result == result and result not in (float("inf"), float("-inf")) else None


def batch_id_for(host: str, collected_at: Any, batch_index: Any) -> str:
    raw = f"{host}|{collected_at}|{batch_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def _backfill_times(run: Dict[str, Any], collected_at: Optional[datetime]) -> None:
    """Guarantee started_at, whatever the sender left out.

    Every time-windowed query filters on started_at, so a row without one is
    invisible in the summary, the timeline and the recent-runs table while the
    hourly rollup still counts it -- the two grains then disagree about how
    much ran.

    The ADK recorder already derives this, but not every sender is the ADK: a
    public HF Space ships a deliberately self-contained reporter, and reports
    only a duration. Doing it here makes the guarantee hold for any client,
    including ones that do not exist yet.

    Preference order, most to least truthful: what the sender said, the end
    time minus the measured duration, the end time, when the batch was
    collected, and finally now.
    """
    started = _coerce_dt(run.get("started_at"))
    if started is not None:
        return

    ended = _coerce_dt(run.get("ended_at"))
    duration = _as_float(run.get("duration_ms"))

    if ended is not None and duration:
        run["started_at"] = ended - timedelta(milliseconds=duration)
    elif ended is not None:
        run["started_at"] = ended
    elif collected_at is not None:
        # Ingest time, not event time -- but a batch is collected within the
        # hour it describes, so the rollup bucket still lands correctly.
        run["started_at"] = collected_at - timedelta(milliseconds=duration or 0)
    else:
        run["started_at"] = datetime.now(timezone.utc)

    if run.get("ended_at") is None:
        run["ended_at"] = _coerce_dt(run["started_at"]) + timedelta(milliseconds=duration or 0)


async def store_run_batch(batch: Dict[str, Any]) -> Dict[str, Any]:
    await ensure_schema()

    host = str(batch.get("host") or "unknown")
    collected_raw = batch.get("collectedAt") or batch.get("collected_at")
    collected_at = _coerce_dt(collected_raw)
    batch_index = _as_int(batch.get("batchIndex") or batch.get("batch_index")) or 0
    runs: List[Dict[str, Any]] = batch.get("runs") or []
    bid = batch_id_for(host, collected_raw, batch_index)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO ai_run_batch_receipts
                    (batch_id, source, schema_version, host, batch_index,
                     collected_at, run_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (batch_id) DO UPDATE
                    SET run_count = EXCLUDED.run_count,
                        received_at = now()
                """,
                bid,
                str(batch.get("source") or "vw-ai-runs"),
                _as_int(batch.get("schema")) or 1,
                host,
                batch_index,
                collected_at,
                len(runs),
            )

            rows = []
            for run in runs:
                if not run.get("run_id"):
                    continue  # unidentifiable; cannot dedupe it, so drop it
                _backfill_times(run, collected_at)
                values: List[Any] = []
                for column in _COLUMNS:
                    raw = run.get(column)
                    if column in _TIMESTAMPS:
                        values.append(_coerce_dt(raw))
                    elif column in _INTS:
                        values.append(_as_int(raw))
                    elif column in _FLOATS:
                        values.append(_as_float(raw))
                    elif column == "host":
                        values.append(str(raw or host))
                    elif column in ("provider", "runtime", "model"):
                        values.append(str(raw or "unknown"))
                    elif column == "status":
                        values.append(str(raw or "ok"))
                    elif column == "cost_state":
                        values.append(str(raw or "settled"))
                    elif column in _BOOLS:
                        values.append(bool(raw) if raw is not None else None)
                    else:
                        values.append(raw)

                tags = run.get("tags") or []
                if not isinstance(tags, list):
                    tags = [str(tags)]
                extra = {k: v for k, v in run.items() if k not in _KNOWN and v is not None}
                if isinstance(run.get("extra"), dict):
                    extra.update(run["extra"])

                values.append([str(t) for t in tags])
                values.append(json.dumps(extra, default=str))
                values.append(bid)
                rows.append(tuple(values))

            if rows:
                placeholders = ", ".join(f"${i}" for i in range(1, len(_COLUMNS) + 1))
                tags_ph = f"${len(_COLUMNS) + 1}"
                extra_ph = f"${len(_COLUMNS) + 2}"
                batch_ph = f"${len(_COLUMNS) + 3}"
                await conn.executemany(
                    f"""
                    INSERT INTO ai_runs ({", ".join(_COLUMNS)}, tags, extra, batch_id)
                    VALUES ({placeholders}, {tags_ph}, {extra_ph}::jsonb, {batch_ph})
                    -- Untargeted on purpose: run_id is the primary key, but
                    -- request_id carries its own unique index, and a replayed
                    -- spool file must be a no-op on *either* collision rather
                    -- than raising a unique violation.
                    ON CONFLICT DO NOTHING
                    """,
                    rows,
                )

    return {"batch_id": bid, "stored": len(rows), "received": len(runs)}


# --------------------------------------------------------------- read side

# Filters every read endpoint accepts, mapped to their SQL predicate.
_FILTERS = {
    "provider": "provider = {}",
    "runtime": "runtime = {}",
    "model": "model = {}",
    "task": "task = {}",
    "project": "lower(project) = lower({})",
    "host": "host = {}",
    "status": "status = {}",
}


# Observations, not invocations. The Ollama poller samples /api/ps to report
# which models are resident and how much VRAM they hold; that is real data, but
# a loaded model is not a run. Counting it as one inflates every volume,
# latency and failure figure with work nothing actually did. Excluded from the
# aggregates by default; ask for task=residency explicitly to see it.
OBSERVATION_TASKS = ("residency",)


def _where(days: Optional[int], filters: Optional[Dict[str, Any]] = None) -> Tuple[str, List[Any]]:
    clauses: List[str] = []
    params: List[Any] = []

    if not (filters or {}).get("task"):
        params.append(list(OBSERVATION_TASKS))
        clauses.append(f"(task IS NULL OR task <> ALL(${len(params)}::text[]))")
    if days:
        params.append(int(days))
        # make_interval rather than ($n || ' days')::interval: the concatenation
        # makes Postgres infer the parameter as TEXT, so asyncpg rejects the int
        # it is actually given.
        clauses.append(f"started_at >= now() - make_interval(days => ${len(params)}::int)")
    for key, value in (filters or {}).items():
        template = _FILTERS.get(key)
        if template and value:
            params.append(value)
            clauses.append(template.format(f"${len(params)}"))
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


async def _group(conn, column: str, where: str, params: Sequence[Any], limit: int = 40) -> List[Dict[str, Any]]:
    """Runs + tokens + cost + failure count + median latency, grouped one way.

    Percentiles are computed here rather than in the client because the raw
    duration column is the one thing we never ship to the browser.
    """
    rows = await conn.fetch(
        f"""
        SELECT COALESCE({column}, 'unknown') AS key,
               count(*) AS runs,
               count(*) FILTER (WHERE status <> 'ok') AS failures,
               COALESCE(sum(total_tokens), 0) AS tokens,
               COALESCE(sum(cost_usd), 0) AS cost_usd,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
               avg(tokens_per_second) AS avg_tps,
               max(started_at) AS latest
        FROM ai_runs
        {where}
        GROUP BY 1
        ORDER BY runs DESC
        LIMIT {int(limit)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def get_summary(days: Optional[int] = None, filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    await ensure_schema()
    where, params = _where(days, filters)
    pool = await get_pool()
    async with pool.acquire() as conn:
        totals = await conn.fetchrow(
            f"""
            SELECT count(*) AS runs,
                   count(*) FILTER (WHERE status = 'ok') AS ok,
                   count(*) FILTER (WHERE status = 'error') AS errors,
                   count(*) FILTER (WHERE status = 'timeout') AS timeouts,
                   count(*) FILTER (WHERE status = 'rejected') AS rejected,
                   count(*) FILTER (WHERE status = 'cancelled') AS cancelled,
                   count(DISTINCT model) AS models,
                   count(DISTINCT provider) AS providers,
                   count(DISTINCT host) AS hosts,
                   COALESCE(sum(input_tokens), 0) AS input_tokens,
                   COALESCE(sum(output_tokens), 0) AS output_tokens,
                   COALESCE(sum(cached_input_tokens), 0) AS cached_input_tokens,
                   COALESCE(sum(reasoning_tokens), 0) AS reasoning_tokens,
                   COALESCE(sum(total_tokens), 0) AS total_tokens,
                   COALESCE(sum(cost_usd), 0) AS cost_usd,
                   COALESCE(sum(duration_ms) / 1000.0, 0) AS compute_seconds,
                   avg(duration_ms) AS avg_ms,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms,
                   percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms) AS p99_ms,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY ttft_ms) AS p50_ttft_ms,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY ttft_ms) AS p95_ttft_ms,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY queue_ms) AS p50_queue_ms,
                   avg(tokens_per_second) AS avg_tps,
                   max(vram_peak_mb) AS peak_vram_mb,
                   avg(gpu_util_pct) AS avg_gpu_util,
                   min(started_at) AS earliest,
                   max(started_at) AS latest
            FROM ai_runs
            {where}
            """,
            *params,
        )
        return {
            "totals": dict(totals) if totals else {},
            "by_provider": await _group(conn, "provider", where, params),
            "by_runtime": await _group(conn, "runtime", where, params),
            "by_model": await _group(conn, "model", where, params, limit=25),
            "by_task": await _group(conn, "task", where, params),
            "by_host": await _group(conn, "host", where, params),
            "by_project": await _group(conn, "project", where, params, limit=25),
            "by_status": await _group(conn, "status", where, params),
        }


async def get_timeline(
    bucket: str = "day", days: int = 30, filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    await ensure_schema()
    # Whitelisted: this value is interpolated into the SQL, never parameterised.
    if bucket not in {"hour", "day", "week", "month"}:
        bucket = "day"
    where, params = _where(days, filters)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT date_trunc('{bucket}', started_at) AS bucket,
                   provider,
                   count(*) AS runs,
                   count(*) FILTER (WHERE status <> 'ok') AS failures,
                   COALESCE(sum(total_tokens), 0) AS tokens,
                   COALESCE(sum(cost_usd), 0) AS cost_usd,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms) AS p50_ms,
                   percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
            FROM ai_runs
            {where}
            GROUP BY 1, 2
            HAVING date_trunc('{bucket}', started_at) IS NOT NULL
            ORDER BY 1
            """,
            *params,
        )
    return {"bucket": bucket, "points": [dict(r) for r in rows]}


async def get_latency_histogram(
    days: Optional[int] = 30, filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Log-ish duration buckets for the distribution widget.

    Fixed edges rather than width_bucket over min/max: model latencies span
    milliseconds (embeddings) to minutes (video), so linear bins would put
    everything in the first bucket.
    """
    await ensure_schema()
    where, params = _where(days, filters)
    extra = "AND duration_ms IS NOT NULL" if where else "WHERE duration_ms IS NOT NULL"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            WITH filtered AS (
                SELECT duration_ms FROM ai_runs {where} {extra}
            ),
            edges AS (
                SELECT unnest(ARRAY[0, 50, 100, 250, 500, 1000, 2500, 5000,
                                    10000, 30000, 60000, 300000]::double precision[]) AS lo
            ),
            bounded AS (
                SELECT lo, lead(lo) OVER (ORDER BY lo) AS hi FROM edges
            )
            SELECT b.lo, b.hi, count(f.duration_ms) AS runs
            FROM bounded b
            LEFT JOIN filtered f
                   ON f.duration_ms >= b.lo
                  AND (b.hi IS NULL OR f.duration_ms < b.hi)
            GROUP BY b.lo, b.hi
            ORDER BY b.lo
            """,
            *params,
        )
    return {"buckets": [dict(r) for r in rows]}


async def get_errors(days: Optional[int] = 30, limit: int = 20,
                     filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    await ensure_schema()
    where, params = _where(days, filters)
    joiner = "AND" if where else "WHERE"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT COALESCE(error_class, 'unknown') AS error_class,
                   status,
                   count(*) AS runs,
                   count(DISTINCT model) AS models,
                   max(started_at) AS latest,
                   (array_agg(error_message ORDER BY started_at DESC)
                        FILTER (WHERE error_message IS NOT NULL))[1] AS last_message,
                   (array_agg(model ORDER BY started_at DESC))[1] AS last_model
            FROM ai_runs
            {where} {joiner} status <> 'ok'
            GROUP BY 1, 2
            ORDER BY runs DESC
            LIMIT {int(limit)}
            """,
            *params,
        )
    return {"errors": [dict(r) for r in rows]}


async def search_runs(
    days: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    await ensure_schema()
    where, params = _where(days, filters)
    params.extend([min(max(limit, 1), 500), max(offset, 0)])
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT run_id, provider, runtime, model, task, project, host, status,
                   error_class, started_at, duration_ms, ttft_ms, queue_ms,
                   input_tokens, output_tokens, total_tokens, tokens_per_second,
                   cost_usd, vram_peak_mb, gpu_name
            FROM ai_runs
            {where}
            ORDER BY started_at DESC NULLS LAST
            LIMIT ${len(params) - 1} OFFSET ${len(params)}
            """,
            *params,
        )
    return {"runs": [dict(r) for r in rows]}
