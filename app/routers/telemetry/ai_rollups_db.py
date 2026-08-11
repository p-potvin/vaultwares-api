"""Persistence for hourly model-run rollups, and cost reconciliation.

Rollup ingest is an idempotent OVERWRITE: a host ships an hour only once that
hour has closed, so the figure it sends is final for that host. Adding on
conflict would double-count every replayed spool file, and the drain is
at-least-once by design.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .ai_runs_db import _as_float, _as_int, _coerce_dt, batch_id_for
from .db import get_pool

_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_SQL = _ROOT / "migrations" / "telemetry" / "005_ai_run_rollups.sql"
_schema_ready = False

_KEY = ("hour", "host", "provider", "runtime", "model", "task", "project", "status")

_COUNTERS = (
    "runs", "failures", "retries", "free_runs", "input_tokens", "output_tokens",
    "cached_input_tokens", "reasoning_tokens", "total_tokens", "ttft_ms_count",
    "queue_ms_count", "tokens_per_second_count", "gpu_util_pct_count",
)
_MEASURES = (
    "cost_usd", "cost_usd_provisional", "duration_ms_sum", "duration_ms_min",
    "duration_ms_max", "ttft_ms_sum", "ttft_ms_max", "queue_ms_sum",
    "tokens_per_second_sum", "vram_peak_mb_max", "gpu_util_pct_sum",
)
_COLUMNS: Tuple[str, ...] = _KEY + _COUNTERS + _MEASURES + ("duration_hist",)


async def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))
    _schema_ready = True


async def store_rollup_batch(batch: Dict[str, Any]) -> Dict[str, Any]:
    await ensure_schema()

    host = str(batch.get("host") or "unknown")
    collected_raw = batch.get("collectedAt") or batch.get("collected_at")
    batch_index = _as_int(batch.get("batchIndex") or batch.get("batch_index")) or 0
    rollups: List[Dict[str, Any]] = batch.get("rollups") or []
    bid = batch_id_for(host, collected_raw, batch_index)

    rows = []
    for entry in rollups:
        hour = _coerce_dt(entry.get("hour"))
        if hour is None:
            continue  # unbucketable; nothing sensible to key it on
        values: List[Any] = [hour]
        for column in _KEY[1:]:
            values.append(str(entry.get(column) or ("unknown" if column != "host" else host)))
        for column in _COUNTERS:
            values.append(_as_int(entry.get(column)) or 0)
        for column in _MEASURES:
            raw = _as_float(entry.get(column))
            # min/max are genuinely absent when nothing reported them; the
            # sums default to 0 because "no cost" and "zero cost" agree.
            if raw is None and column.endswith(("_min", "_max")):
                values.append(None)
            else:
                values.append(raw or 0.0)
        hist = entry.get("duration_hist") or []
        values.append([int(x) for x in hist] if isinstance(hist, list) else [])
        rows.append(tuple(values))

    if not rows:
        return {"batch_id": bid, "stored": 0, "received": len(rollups)}

    placeholders = ", ".join(f"${i}" for i in range(1, len(_COLUMNS) + 1))
    updates = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in _COUNTERS + _MEASURES + ("duration_hist",)
    )

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.executemany(
                f"""
                INSERT INTO ai_run_rollups ({", ".join(_COLUMNS)})
                VALUES ({placeholders})
                ON CONFLICT (hour, host, provider, runtime, model, task, project, status)
                DO UPDATE SET {updates}, updated_at = now()
                """,
                rows,
            )
    return {"batch_id": bid, "stored": len(rows), "received": len(rollups)}


# ------------------------------------------------------------- reconciliation


async def settle_costs(
    request_ids: Sequence[str],
    cost_usd: float,
    *,
    billing_source: Optional[str] = None,
) -> Dict[str, Any]:
    """Replace provisional costs with a settled total, split across the rows.

    Mirrors vault-inference's ``budget.settle()`` deliberately:

    * only rows still marked provisional are touched — **an already-settled row
      is never rewritten**, because the drain is at-least-once and a second
      settle would double-count;
    * one settled total is divided across the rows it covers rather than
      dumped on one, so per-project attribution survives reconciliation.
    """
    await ensure_schema()
    ids = [str(r) for r in request_ids if r]
    if not ids:
        return {"settled": 0, "skipped": 0, "per_row": 0.0}

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock the candidate rows so a concurrent settle cannot also see
            # them as provisional and apply a second split.
            targets = await conn.fetch(
                """
                SELECT run_id, project, hour_bucket FROM (
                    SELECT run_id, project, date_trunc('hour', started_at) AS hour_bucket
                    FROM ai_runs
                    WHERE request_id = ANY($1::text[]) AND cost_state = 'provisional'
                    FOR UPDATE
                ) t
                """,
                ids,
            )
            if not targets:
                return {"settled": 0, "skipped": len(ids), "per_row": 0.0}

            per_row = float(cost_usd) / len(targets)
            await conn.execute(
                """
                UPDATE ai_runs
                   SET cost_usd = $2,
                       cost_state = 'settled',
                       priced_exactly = TRUE,
                       billing_source = COALESCE($3, billing_source)
                 WHERE request_id = ANY($1::text[]) AND cost_state = 'provisional'
                """,
                ids,
                per_row,
                billing_source,
            )

            # The rollup for those hours now disagrees with the raw rows, so
            # recompute the affected cells rather than leaving stale spend on
            # the durable grain.
            hours = sorted({row["hour_bucket"] for row in targets if row["hour_bucket"]})
            if hours:
                await _recompute_rollup_costs(conn, hours)

    return {"settled": len(targets), "skipped": len(ids) - len(targets), "per_row": per_row}


async def _recompute_rollup_costs(conn, hours: List[datetime]) -> None:
    """Rewrite cost columns of the rollup cells covering these hours."""
    await conn.execute(
        """
        WITH fresh AS (
            SELECT date_trunc('hour', started_at) AS hour,
                   host, provider, runtime, model,
                   COALESCE(task, 'unknown') AS task,
                   COALESCE(project, 'unknown') AS project,
                   status,
                   SUM(CASE WHEN cost_state = 'settled'
                            THEN COALESCE(cost_usd, 0) ELSE 0 END) AS settled,
                   SUM(CASE WHEN cost_state <> 'settled'
                            THEN COALESCE(cost_usd, 0) ELSE 0 END) AS provisional
            FROM ai_runs
            WHERE date_trunc('hour', started_at) = ANY($1::timestamptz[])
            GROUP BY 1,2,3,4,5,6,7,8
        )
        UPDATE ai_run_rollups r
           SET cost_usd = fresh.settled,
               cost_usd_provisional = fresh.provisional,
               updated_at = now()
          FROM fresh
         WHERE r.hour = fresh.hour
           AND r.host = fresh.host
           AND r.provider = fresh.provider
           AND r.runtime = fresh.runtime
           AND r.model = fresh.model
           AND r.task = fresh.task
           AND r.project = fresh.project
           AND r.status = fresh.status
        """,
        hours,
    )


async def provisional_runs(limit: int = 500, days: int = 30) -> Dict[str, Any]:
    """Rows still awaiting a settled cost — the input to the hourly pass."""
    await ensure_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT run_id, request_id, provider, model, project, task,
                   started_at, cost_usd
            FROM ai_runs
            WHERE cost_state <> 'settled'
              AND started_at >= now() - make_interval(days => $2::int)
            ORDER BY started_at
            LIMIT $1
            """,
            min(max(limit, 1), 2000),
            int(days),
        )
    return {"runs": [dict(r) for r in rows], "count": len(rows)}


# ------------------------------------------------------------------ read side


async def get_rollup_timeline(
    days: int = 90, bucket: str = "day", filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Timeline served from the hourly grain, for windows too long to scan raw."""
    await ensure_schema()
    if bucket not in {"hour", "day", "week", "month"}:
        bucket = "day"

    # make_interval, not ($1 || ' days')::interval — the concatenation makes
    # Postgres infer the parameter as TEXT and asyncpg then rejects the int.
    clauses = ["hour >= now() - make_interval(days => $1::int)"]
    params: List[Any] = [int(days)]
    for key in ("provider", "runtime", "model", "project"):
        value = (filters or {}).get(key)
        if value:
            params.append(value)
            clauses.append(f"{key} = ${len(params)}")
    where = "WHERE " + " AND ".join(clauses)

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT date_trunc('{bucket}', hour) AS bucket,
                   provider,
                   SUM(runs) AS runs,
                   SUM(failures) AS failures,
                   SUM(total_tokens) AS tokens,
                   SUM(cost_usd) AS cost_usd,
                   SUM(cost_usd_provisional) AS cost_usd_provisional,
                   -- Weighted by count, so an hour with three runs does not
                   -- swing the mean as hard as one with three thousand.
                   CASE WHEN SUM(runs) > 0
                        THEN SUM(duration_ms_sum) / SUM(runs) END AS avg_ms,
                   CASE WHEN SUM(ttft_ms_count) > 0
                        THEN SUM(ttft_ms_sum) / SUM(ttft_ms_count) END AS avg_ttft_ms,
                   MAX(duration_ms_max) AS max_ms
            FROM ai_run_rollups
            {where}
            GROUP BY 1, 2
            ORDER BY 1
            """,
            *params,
        )
    return {"bucket": bucket, "grain": "hour", "points": [dict(r) for r in rows]}
