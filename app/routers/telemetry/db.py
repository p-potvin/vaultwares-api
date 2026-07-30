from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None
_schema_ready = False
_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_SQL = _ROOT / "migrations" / "telemetry" / "001_input_telemetry.sql"


def _dsn() -> str:
    dsn = os.environ.get("VW_TELEMETRY_DATABASE_URL") or os.environ.get("DB_URL") or ""
    if dsn.startswith("postgresql://"):
        dsn = "postgres://" + dsn[len("postgresql://") :]
    return dsn


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = _dsn()
        if not dsn:
            raise RuntimeError("VW_TELEMETRY_DATABASE_URL or DB_URL is required")
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)
    return _pool


async def close_pool() -> None:
    global _pool, _schema_ready
    if _pool is not None:
        await _pool.close()
    _pool = None
    _schema_ready = False


async def ensure_schema() -> None:
    global _schema_ready
    if _schema_ready:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL.read_text(encoding="utf-8"))
    _schema_ready = True


def _json(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, separators=(",", ":"), default=str)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


def _coerce_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _checksum(event: Dict[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "checksum"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _natural_path_record(batch: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
    metrics = _as_dict(event.get("metrics"))
    dimensions = _as_dict(event.get("dimensions"))
    stats = _as_dict(metrics.get("stats"))
    return {
        "path_id": str(metrics.get("path_id") or event["event_id"]),
        "event_id": event["event_id"],
        "batch_id": batch["batch_id"],
        "session_id": batch["session_id"],
        "source": batch["source"],
        "trigger": str(metrics.get("trigger") or dimensions.get("trigger") or "unknown"),
        "started_at": _coerce_dt(metrics.get("started_at")) or _coerce_dt(event.get("bucket_start")) or _coerce_dt(event.get("timestamp")),
        "ended_at": _coerce_dt(metrics.get("ended_at")) or _coerce_dt(event.get("timestamp")),
        "duration_ms": int(float(metrics.get("duration_ms") or stats.get("duration_ms") or 0)),
        "start_context": _as_dict(dimensions.get("start_context")),
        "end_context": _as_dict(dimensions.get("end_context")),
        "mouse_path": _as_list(metrics.get("mouse_path")),
        "key_presses": _as_list(metrics.get("key_presses")),
        "click_target": _as_dict(metrics.get("click_target")),
        "stats": stats,
    }


async def store_input_batch(batch: Dict[str, Any]) -> Dict[str, Any]:
    if os.environ.get("VW_TELEMETRY_AUTO_SCHEMA", "1") == "1":
        await ensure_schema()
    pool = await get_pool()
    inserted = 0
    duplicates = 0
    events = batch.get("events") or []
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO input_batch_receipts
                  (batch_id, session_id, source, schema_version, host, started_at, ended_at, event_count)
                VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7, $8)
                ON CONFLICT (batch_id) DO UPDATE SET
                  event_count = GREATEST(input_batch_receipts.event_count, EXCLUDED.event_count),
                  ended_at = COALESCE(EXCLUDED.ended_at, input_batch_receipts.ended_at)
                """,
                batch["batch_id"],
                batch["session_id"],
                batch["source"],
                batch["schema_version"],
                _json(batch.get("host")),
                batch.get("started_at"),
                batch.get("ended_at"),
                len(events),
            )
            for event in events:
                result = await conn.execute(
                    """
                    INSERT INTO input_events
                      (event_id, batch_id, session_id, source, event_type, timestamp, bucket_start, metrics, dimensions, checksum)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10)
                    ON CONFLICT (event_id) DO NOTHING
                    """,
                    event["event_id"],
                    batch["batch_id"],
                    batch["session_id"],
                    batch["source"],
                    event["event_type"],
                    event.get("timestamp"),
                    event.get("bucket_start"),
                    _json(event.get("metrics")),
                    _json(event.get("dimensions")),
                    event.get("checksum") or _checksum(event),
                )
                if result.endswith("1"):
                    inserted += 1
                    if event["event_type"] == "minute_rollup":
                        await conn.execute(
                            """
                            INSERT INTO input_minute_rollups
                              (event_id, bucket_start, metrics, dimensions)
                            VALUES ($1, $2, $3::jsonb, $4::jsonb)
                            ON CONFLICT (event_id) DO NOTHING
                            """,
                            event["event_id"],
                            event.get("bucket_start") or event.get("timestamp"),
                            _json(event.get("metrics")),
                            _json(event.get("dimensions")),
                        )
                    elif event["event_type"] == "natural_path":
                        path = _natural_path_record(batch, event)
                        await conn.execute(
                            """
                            INSERT INTO natural_paths
                              (path_id, event_id, batch_id, session_id, source, trigger, started_at, ended_at,
                               duration_ms, start_context, end_context, mouse_path, key_presses, click_target, stats)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11::jsonb, $12::jsonb, $13::jsonb, $14::jsonb, $15::jsonb)
                            ON CONFLICT (path_id) DO NOTHING
                            """,
                            path["path_id"],
                            path["event_id"],
                            path["batch_id"],
                            path["session_id"],
                            path["source"],
                            path["trigger"],
                            path["started_at"],
                            path["ended_at"],
                            path["duration_ms"],
                            _json(path["start_context"]),
                            _json(path["end_context"]),
                            _json(path["mouse_path"]),
                            _json(path["key_presses"]),
                            _json(path["click_target"]),
                            _json(path["stats"]),
                        )
                else:
                    duplicates += 1
    return {"batch_id": batch["batch_id"], "inserted": inserted, "duplicates": duplicates, "received": len(events)}


# ── Input-summary SQL building blocks ────────────────────────────────────────
# Aggregates are computed in Postgres rather than by pulling rows into Python.
# The previous implementation fetched `LIMIT 2000` minute rollups and summed
# them here, which silently capped every total/KPI at the most recent ~2000
# minutes (~33h) no matter how wide a window the caller asked for.

_EVENT_TS_SQL = "COALESCE(bucket_start, timestamp, received_at)"

# Mirrors _duration_weight(): max(1.0, active_seconds or duration_seconds).
_WEIGHT_SQL = """
    GREATEST(
        1.0,
        COALESCE(
            NULLIF(
                CASE WHEN jsonb_typeof(metrics -> 'active_seconds') = 'number'
                     THEN (metrics ->> 'active_seconds')::float8 END,
                0
            ),
            CASE WHEN jsonb_typeof(metrics -> 'duration_seconds') = 'number'
                 THEN (metrics ->> 'duration_seconds')::float8 END,
            0
        )
    )
"""


def _jsonb_number(expr: str) -> str:
    """Read a JSONB value as float8, yielding 0 for non-numeric entries."""
    return f"CASE WHEN jsonb_typeof({expr}) = 'number' THEN ({expr} #>> '{{}}')::float8 ELSE 0 END"


def _num(metrics: Dict[str, Any], key: str) -> float:
    try:
        return float(metrics.get(key, 0) or 0)
    except Exception:
        return 0.0


def _row_dt(row: Any, key: str) -> datetime | None:
    try:
        value = row[key]
    except Exception:
        value = None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


# NOTE: _sum_numeric_metrics / _bucket_counts / _window_counts are the readable
# reference implementations of the aggregations get_input_summary() now performs
# in SQL (see _WEIGHT_SQL and the queries below). They are no longer on the
# request path; they remain as executable documentation of the intended
# semantics and are covered by tests/test_telemetry_input_router.py. Any change
# to the SQL aggregation should be mirrored here, and vice versa.
def _sum_numeric_metrics(rows: Iterable[Any]) -> Dict[str, float]:
    totals: Dict[str, float] = {}
    for row in rows:
        metrics = _as_dict(row["metrics"])
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0.0) + float(value)
    return totals


def _duration_weight(metrics: Dict[str, Any]) -> float:
    return max(1.0, _num(metrics, "active_seconds") or _num(metrics, "duration_seconds"))


def _bucket_counts(rows: Iterable[Any], key: str) -> list[dict[str, Any]]:
    counts: Dict[str, float] = {}
    for row in rows:
        metrics = _as_dict(row["metrics"])
        dimensions = _as_dict(row["dimensions"])
        bucket = str(dimensions.get(key) or "unknown")
        counts[bucket] = counts.get(bucket, 0.0) + _duration_weight(metrics)
    return [{"name": name, "count": round(count, 2)} for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)]


def _window_counts(rows: Iterable[Any]) -> list[dict[str, Any]]:
    counts: Dict[tuple[str, str], float] = {}
    for row in rows:
        metrics = _as_dict(row["metrics"])
        dimensions = _as_dict(row["dimensions"])
        category = str(dimensions.get("focus_category") or "unknown")
        name = str(dimensions.get("window_name") or dimensions.get("window_app") or "unknown")
        key = (category, name)
        counts[key] = counts.get(key, 0.0) + _duration_weight(metrics)
    return [
        {"category": category, "name": name, "count": round(count, 2)}
        for (category, name), count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:20]
    ]


def _max_metric(rows: Iterable[Any], key: str) -> float:
    values = [_num(_as_dict(row["metrics"]), key) for row in rows]
    return max(values) if values else 0.0


def _hotspot_buckets(rows: Iterable[Any]) -> Dict[str, float]:
    hotspots: Dict[str, float] = {}
    for row in rows:
        metrics = _as_dict(row["metrics"])
        for key, value in (metrics.get("click_hotspots") or {}).items():
            hotspots[key] = hotspots.get(key, 0.0) + float(value or 0)
    return hotspots


def _hotspot_peak(rows: Iterable[Any]) -> float:
    """Largest single click-hotspot bucket, summed across rows."""
    buckets = _hotspot_buckets(rows)
    return max(buckets.values()) if buckets else 0.0


def _hotspot_total(rows: Iterable[Any]) -> float:
    """Clicks actually attributed to a hotspot bucket."""
    return sum(_hotspot_buckets(rows).values())


def _natural_path_summary(
    totals: Any,
    trigger_rows: Iterable[Any],
) -> Dict[str, Any]:
    count = int((totals["path_count"] if totals else 0) or 0)
    latest_started = totals["latest_started_at"] if totals else None
    return {
        "count": count,
        "latest_started_at": latest_started.isoformat() if latest_started else None,
        "triggers": [{"name": row["name"], "count": int(row["count"])} for row in trigger_rows],
        "avg_duration_seconds": round((float((totals["duration_ms"] if totals else 0) or 0) / max(1, count)) / 1000.0, 2),
        "avg_points": round(float((totals["points"] if totals else 0) or 0) / max(1, count), 2),
        "avg_keys": round(float((totals["keys"] if totals else 0) or 0) / max(1, count), 2),
        "total_distance_m": round(float((totals["distance_m"] if totals else 0) or 0), 4),
    }


def _kpi_signals(
    rows: Iterable[Any],
    totals: Dict[str, float],
    *,
    hours: int,
    latest_received_at: datetime | None,
    generated_at: datetime,
    peaks: Dict[str, float] | None = None,
    hotspot_peak: float | None = None,
    hotspot_total: float | None = None,
    best_hour: int | None = None,
    best_day: str | None = None,
    active_day_count: int | None = None,
    sample_count: int | None = None,
    expected_minutes: int | None = None,
    late_night_minutes: float | None = None,
    weekly_consistency: float | None = None,
    ramp_up_minutes: float | None = None,
) -> Dict[str, Any]:
    """Derive KPI signals.

    The keyword arguments let a caller supply values already aggregated in SQL
    over the *full* window. When omitted they are derived from ``rows``, which
    keeps the pure-Python path (and its unit tests) working unchanged.
    """
    rows_list = list(rows)
    active_minutes = max(0.0, totals.get("active_seconds", 0.0) / 60.0)
    active_hours = active_minutes / 60.0
    context_switches = totals.get("context_switches", 0.0)
    chars_typed = totals.get("chars_typed", 0.0)
    chars_pasted = totals.get("chars_pasted", 0.0)
    keystrokes = totals.get("keystrokes", 0.0)
    clicks = totals.get("clicks", 0.0)
    focus_streak_samples = totals.get("focus_streak_samples", 0.0)
    recovery_samples = totals.get("switch_recovery_samples", 0.0)

    if best_hour is None or best_day is None or active_day_count is None:
        active_by_hour: Dict[int, float] = {}
        active_by_day: Dict[str, float] = {}
        for row in rows_list:
            timestamp = _row_dt(row, "bucket_start") or _row_dt(row, "timestamp") or _row_dt(row, "received_at")
            if not timestamp:
                continue
            active = _duration_weight(_as_dict(row["metrics"]))
            active_by_hour[timestamp.hour] = active_by_hour.get(timestamp.hour, 0.0) + active
            day = timestamp.date().isoformat()
            active_by_day[day] = active_by_day.get(day, 0.0) + active

        if best_hour is None:
            best_hour = max(active_by_hour.items(), key=lambda item: item[1])[0] if active_by_hour else None
        if best_day is None:
            best_day = max(active_by_day.items(), key=lambda item: item[1])[0] if active_by_day else None
        if active_day_count is None:
            active_day_count = len(active_by_day)

    def peak(key: str) -> float:
        return peaks.get(key, 0.0) if peaks is not None else _max_metric(rows_list, key)

    if sample_count is None:
        sample_count = len(rows_list)
    if expected_minutes is None:
        expected_minutes = max(1, hours * 60)
    if hotspot_peak is None:
        hotspot_peak = _hotspot_peak(rows_list)
    if hotspot_total is None:
        hotspot_total = _hotspot_total(rows_list)

    lag_minutes = 0.0
    if latest_received_at:
        lag_minutes = max(0.0, (generated_at - latest_received_at).total_seconds() / 60.0)

    return {
        "focus": {
            # Per *active* hour, not wall-clock hour. Wall-clock included idle
            # time, so this could not be reconciled with flow stability
            # (active minutes per switch); the two are now exact reciprocals.
            "context_switches_per_hour": round(context_switches / max(0.01, active_hours), 2),
            "avg_focus_minutes_per_switch": round(active_minutes / max(1.0, context_switches), 2),
            "longest_focus_block_minutes": round(peak("longest_focus_streak_seconds") / 60.0, 2),
            "avg_recorded_focus_streak_minutes": round(
                (totals.get("focus_streak_seconds_total", 0.0) / max(1.0, focus_streak_samples)) / 60.0,
                2,
            ),
            "avg_switch_recovery_seconds": round(
                totals.get("switch_recovery_seconds_total", 0.0) / max(1.0, recovery_samples),
                2,
            ),
            "longest_active_block_minutes": round(peak("longest_active_block_seconds") / 60.0, 2),
        },
        "typing": {
            "paste_share": round(chars_pasted / max(1.0, chars_typed + chars_pasted), 4),
            "shortcut_density_per_1000_keys": round((totals.get("shortcut_count", 0.0) / max(1.0, keystrokes)) * 1000.0, 2),
            "save_cadence_minutes": round(active_minutes / max(1.0, totals.get("saves", 0.0)), 2),
            "undo_redo_per_1000_keys": round((totals.get("undo_redo", 0.0) / max(1.0, keystrokes)) * 1000.0, 2),
        },
        "pointer": {
            "clicks_per_active_minute": round(clicks / max(1.0, active_minutes), 2),
            "scrolls_per_active_minute": round(totals.get("scroll_ticks", 0.0) / max(1.0, active_minutes), 2),
            "pointer_meters_per_active_hour": round(totals.get("mouse_distance_m", 0.0) / max(0.01, active_hours), 2),
            # Share of *bucketed* clicks, matching the denominator clients use to
            # label each zone on the hotspot grid. Dividing by total clicks
            # instead understated this whenever some clicks landed outside a
            # sampled bucket.
            "hotspot_top_share": round(hotspot_peak / hotspot_total, 4) if hotspot_total > 0 else 0.0,
        },
        "rhythm": {
            "best_hour_utc": best_hour,
            "best_day": best_day,
            "active_minutes_per_day": round(active_minutes / max(1.0, active_day_count), 2),
            "avg_rest_gap_minutes": round((totals.get("rest_gap_seconds_total", 0.0) / max(1.0, totals.get("active_starts_after_rest", 0.0))) / 60.0, 2),
            "longest_rest_gap_minutes": round(peak("rest_gap_seconds_max") / 60.0, 2),
            # Previously absent from the payload entirely, which is why the
            # dashboard rendered "-" for these three.
            "ramp_up_minutes": round(ramp_up_minutes, 2) if ramp_up_minutes is not None else None,
            "weekly_consistency_score": round(weekly_consistency, 4) if weekly_consistency is not None else None,
            "late_night_active_minutes": round(late_night_minutes, 2) if late_night_minutes is not None else None,
        },
        "reliability": {
            # Bounded by definition: it is a share of the window. Clamped so a
            # boundary rounding artefact can never surface as >100% again.
            "data_coverage_percent": round(min(100.0, (sample_count / expected_minutes) * 100.0), 2),
            "missing_minutes_estimate": max(0, expected_minutes - sample_count),
            "batch_lag_minutes": round(lag_minutes, 2),
            "spool_backlog_batches": int(peak("spool_backlog_batches")),
            "spool_backlog_bytes": int(peak("spool_backlog_bytes")),
        },
    }


async def _nested_metric_sums(conn: Any, since: datetime, field: str) -> Dict[str, float]:
    """SUM a nested JSONB map inside metrics (e.g. click_hotspots) by key."""
    rows = await conn.fetch(
        f"""
        SELECT kv.key AS name, SUM({_jsonb_number('kv.value')}) AS total
        FROM input_events
        CROSS JOIN LATERAL jsonb_each(metrics -> '{field}') AS kv
        WHERE {_EVENT_TS_SQL} >= $1
          AND jsonb_typeof(metrics -> '{field}') = 'object'
        GROUP BY kv.key
        """,
        since,
    )
    return {row["name"]: float(row["total"] or 0) for row in rows}


async def get_input_summary(hours: int = 24) -> Dict[str, Any]:
    if os.environ.get("VW_TELEMETRY_AUTO_SCHEMA", "1") == "1":
        await ensure_schema()
    pool = await get_pool()
    generated_at = datetime.now(timezone.utc)
    window_hours = max(1, hours)

    async with pool.acquire() as conn:
        latest_db_row = await conn.fetchrow(
            f"SELECT received_at FROM input_events ORDER BY {_EVENT_TS_SQL} DESC LIMIT 1"
        )
        latest_db_dt = latest_db_row["received_at"] if latest_db_row else None
        if latest_db_dt:
            since = latest_db_dt - timedelta(hours=window_hours)
        else:
            since = generated_at - timedelta(hours=window_hours)
        # Totals and per-key peaks across the whole window, in one pass.
        metric_rows = await conn.fetch(
            f"""
            SELECT kv.key AS name,
                   SUM({_jsonb_number('kv.value')}) AS total,
                   MAX({_jsonb_number('kv.value')}) AS peak
            FROM input_events
            CROSS JOIN LATERAL jsonb_each(metrics) AS kv
            WHERE {_EVENT_TS_SQL} >= $1
              AND jsonb_typeof(kv.value) = 'number'
            GROUP BY kv.key
            """,
            since,
        )
        latency = await _nested_metric_sums(conn, since, "key_latency_buckets")
        hotspots = await _nested_metric_sums(conn, since, "click_hotspots")

        span = await conn.fetchrow(
            f"""
            SELECT COUNT(*) AS event_count,
                   -- Coverage counts *minutes observed*, so it must be distinct
                   -- minute buckets from minute_rollup events only. Counting raw
                   -- rows let natural_path (and any duplicate rollup for the same
                   -- minute) inflate the numerator past 100%.
                   COUNT(DISTINCT date_trunc('minute', {_EVENT_TS_SQL}))
                       FILTER (WHERE event_type = 'minute_rollup') AS covered_minutes,
                   MIN({_EVENT_TS_SQL}) AS first_seen,
                   COUNT(DISTINCT (({_EVENT_TS_SQL}) AT TIME ZONE 'UTC')::date) AS active_days
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
            """,
            since,
        )
        latest_row = await conn.fetchrow(
            f"""
            SELECT received_at
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
            ORDER BY {_EVENT_TS_SQL} DESC
            LIMIT 1
            """,
            since,
        )
        best_hour_row = await conn.fetchrow(
            f"""
            SELECT EXTRACT(HOUR FROM (({_EVENT_TS_SQL}) AT TIME ZONE 'UTC'))::int AS name,
                   SUM({_WEIGHT_SQL}) AS total
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
            GROUP BY 1 ORDER BY total DESC LIMIT 1
            """,
            since,
        )
        # Active seconds logged between 22:00 and 06:00 UTC.
        late_night_row = await conn.fetchrow(
            f"""
            SELECT COALESCE(SUM({_WEIGHT_SQL}), 0) AS total
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
              AND (
                    EXTRACT(HOUR FROM (({_EVENT_TS_SQL}) AT TIME ZONE 'UTC')) >= 22
                 OR EXTRACT(HOUR FROM (({_EVENT_TS_SQL}) AT TIME ZONE 'UTC')) < 6
              )
            """,
            since,
        )
        # Active weight per ISO weekday, for the consistency score.
        weekday_rows = await conn.fetch(
            f"""
            SELECT EXTRACT(ISODOW FROM (({_EVENT_TS_SQL}) AT TIME ZONE 'UTC'))::int AS dow,
                   SUM({_WEIGHT_SQL}) AS total
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
            GROUP BY 1
            """,
            since,
        )
        # First activity vs. first "full" minute of each day, for ramp-up.
        ramp_rows = await conn.fetch(
            f"""
            WITH per_day AS (
                SELECT (({_EVENT_TS_SQL}) AT TIME ZONE 'UTC')::date AS day,
                       {_EVENT_TS_SQL} AS ts,
                       {_WEIGHT_SQL} AS weight
                FROM input_events
                WHERE {_EVENT_TS_SQL} >= $1
                  AND event_type = 'minute_rollup'
            )
            SELECT day,
                   MIN(ts) AS first_ts,
                   MIN(ts) FILTER (WHERE weight >= 48) AS steady_ts
            FROM per_day
            GROUP BY day
            """,
            since,
        )
        best_day_row = await conn.fetchrow(
            f"""
            SELECT (({_EVENT_TS_SQL}) AT TIME ZONE 'UTC')::date AS name,
                   SUM({_WEIGHT_SQL}) AS total
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
            GROUP BY 1 ORDER BY total DESC LIMIT 1
            """,
            since,
        )
        focus_rows = await conn.fetch(
            f"""
            SELECT COALESCE(NULLIF(dimensions ->> 'focus_category', ''), 'unknown') AS name,
                   SUM({_WEIGHT_SQL}) AS total
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
            GROUP BY 1 ORDER BY total DESC
            """,
            since,
        )
        window_rows = await conn.fetch(
            f"""
            SELECT COALESCE(NULLIF(dimensions ->> 'focus_category', ''), 'unknown') AS category,
                   COALESCE(NULLIF(dimensions ->> 'window_name', ''),
                            NULLIF(dimensions ->> 'window_app', ''), 'unknown') AS name,
                   SUM({_WEIGHT_SQL}) AS total
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
            GROUP BY 1, 2 ORDER BY total DESC LIMIT 20
            """,
            since,
        )
        # Display-only tail; the aggregates above already cover the full window.
        event_rows = await conn.fetch(
            f"""
            SELECT event_id, event_type, timestamp, bucket_start, metrics, dimensions, received_at
            FROM input_events
            WHERE {_EVENT_TS_SQL} >= $1
            ORDER BY {_EVENT_TS_SQL} DESC
            LIMIT 100
            """,
            since,
            max_events_limit,
        )
        natural_totals = await conn.fetchrow(
            f"""
            SELECT COUNT(*) AS path_count,
                   MAX(COALESCE(started_at, created_at)) AS latest_started_at,
                   COALESCE(SUM(duration_ms), 0) AS duration_ms,
                   COALESCE(SUM({_jsonb_number("stats -> 'point_count'")}), 0) AS points,
                   COALESCE(SUM({_jsonb_number("stats -> 'key_count'")}), 0) AS keys,
                   COALESCE(SUM({_jsonb_number("stats -> 'distance_m'")}), 0) AS distance_m
            FROM natural_paths
            WHERE COALESCE(started_at, created_at) >= $1
            """,
            since,
            max_paths_limit,
        )
        natural_triggers = await conn.fetch(
            """
            SELECT COALESCE(NULLIF(trigger, ''), 'unknown') AS name, COUNT(*) AS count
            FROM natural_paths
            WHERE COALESCE(started_at, created_at) >= $1
            GROUP BY 1 ORDER BY count DESC
            """,
            since,
        )

    totals = {row["name"]: float(row["total"] or 0) for row in metric_rows}
    peaks = {row["name"]: float(row["peak"] or 0) for row in metric_rows}

    covered_minutes = int(span["covered_minutes"] or 0) if span else 0
    active_days = int(span["active_days"] or 0) if span else 0
    first_seen = span["first_seen"] if span else None

    # ── Rhythm signals ───────────────────────────────────────────────────────
    late_night_minutes = float((late_night_row["total"] if late_night_row else 0) or 0) / 60.0

    # Weekly consistency: normalized entropy of active weight across weekdays.
    # 1.0 = spread perfectly evenly, 0.0 = the entire load on a single day.
    weekday_weights = [float(row["total"] or 0) for row in weekday_rows if (row["total"] or 0) > 0]
    weekly_consistency = None
    if weekday_weights:
        if len(weekday_weights) == 1:
            weekly_consistency = 0.0
        else:
            grand = sum(weekday_weights)
            entropy = -sum((w / grand) * math.log(w / grand) for w in weekday_weights)
            weekly_consistency = entropy / math.log(7)

    # Ramp-up: minutes from a day's first recorded activity to its first
    # near-full active minute (>=48s of 60), averaged over days that reached one.
    ramp_deltas = [
        (row["steady_ts"] - row["first_ts"]).total_seconds() / 60.0
        for row in ramp_rows
        if row["steady_ts"] and row["first_ts"]
    ]
    ramp_up_minutes = sum(ramp_deltas) / len(ramp_deltas) if ramp_deltas else None

    # Coverage is measured against the span actually observable in this window,
    # not the raw request. Asking for 20 years of history when the tracker has
    # only ever recorded a month should not report ~0% coverage.
    observed_hours = (generated_at - first_seen).total_seconds() / 3600.0 if first_seen else 0.0
    effective_hours = min(float(window_hours), observed_hours) if first_seen else float(window_hours)
    # +1 because a span running from the first to the last recorded minute
    # contains one more minute bucket than the elapsed difference between them
    # (1439 minutes elapsed == 1440 distinct minutes observed).
    expected_minutes = max(1, int(round(max(effective_hours, 0.0) * 60)) + (1 if first_seen else 0))

    latest_dt = latest_row["received_at"] if latest_row else None
    latest = latest_dt.isoformat() if latest_dt else None

    active_minutes = max(1.0, totals.get("active_seconds", 0.0) / 60.0)
    chars = totals.get("chars_typed", 0.0)
    clicks = totals.get("clicks", 0.0)
    travel_m = totals.get("mouse_distance_m", 0.0)

    stale = True
    if latest_dt:
        stale = latest_dt < generated_at - timedelta(minutes=10)

    return {
        "source": "vaultwares-api",
        "status": "stale" if stale else "online",
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "latest_received_at": latest,
        "window_hours": window_hours,
        "effective_window_hours": round(effective_hours, 2),
        "totals": {key: round(value, 4) for key, value in totals.items()},
        "derived": {
            "wpm": round((chars / 5.0) / active_minutes, 2),
            "cpm": round(chars / active_minutes, 2),
            "correction_ratio": round((totals.get("backspaces", 0.0) + totals.get("deletes", 0.0)) / max(1.0, chars), 4),
            "click_to_travel_ratio": round(clicks / max(0.001, travel_m), 2),
        },
        "key_latency_buckets": [{"name": key, "count": count} for key, count in sorted(latency.items())],
        "click_hotspots": [
            {"name": key, "count": count}
            for key, count in sorted(hotspots.items(), key=lambda item: item[1], reverse=True)[:20]
        ],
        "natural_paths": _natural_path_summary(natural_totals, natural_triggers),
        "focus_categories": [{"name": row["name"], "count": round(float(row["total"] or 0), 2)} for row in focus_rows],
        "focus_windows": [
            {"category": row["category"], "name": row["name"], "count": round(float(row["total"] or 0), 2)}
            for row in window_rows
        ],
        # Total across *all* hotspot buckets, not just the top 20 returned above.
        # Clients need this as the denominator so their per-zone percentages
        # agree with hotspot_top_share.
        "click_hotspot_total": round(sum(hotspots.values()), 2) if hotspots else 0.0,
        "kpis": _kpi_signals(
            (),
            totals,
            hours=window_hours,
            latest_received_at=latest_dt,
            generated_at=generated_at,
            peaks=peaks,
            hotspot_peak=max(hotspots.values()) if hotspots else 0.0,
            hotspot_total=sum(hotspots.values()) if hotspots else 0.0,
            best_hour=int(best_hour_row["name"]) if best_hour_row and best_hour_row["name"] is not None else None,
            best_day=best_day_row["name"].isoformat() if best_day_row and best_day_row["name"] else None,
            active_day_count=active_days,
            sample_count=covered_minutes,
            expected_minutes=expected_minutes,
            late_night_minutes=late_night_minutes,
            weekly_consistency=weekly_consistency,
            ramp_up_minutes=ramp_up_minutes,
        ),
        "events": [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "timestamp": (row["timestamp"] or row["bucket_start"] or row["received_at"]).isoformat(),
                "metrics": _as_dict(row["metrics"]),
                "dimensions": _as_dict(row["dimensions"]),
            }
            for row in event_rows
        ],
        "privacy": {
            "raw_text": "natural_paths_raw_keys_owner_opt_in",
            "clipboard_contents": False,
            "window_titles": "hashed_or_redacted",
        },
    }


async def search_input_events(q: str = "", event_type: Optional[str] = None, session_id: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
    if os.environ.get("VW_TELEMETRY_AUTO_SCHEMA", "1") == "1":
        await ensure_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_id, batch_id, session_id, source, event_type, timestamp, bucket_start, metrics, dimensions, received_at
            FROM input_events
            WHERE ($1::text IS NULL OR event_type = $1)
              AND ($2::text IS NULL OR session_id = $2)
              AND ($3::text = '' OR metrics::text ILIKE '%' || $3 || '%' OR dimensions::text ILIKE '%' || $3 || '%')
            ORDER BY COALESCE(bucket_start, timestamp, received_at) DESC
            LIMIT $4
            """,
            event_type,
            session_id,
            q,
            max(1, min(limit, 500)),
        )
    return {
        "query": q,
        "count": len(rows),
        "items": [
            {
                "event_id": row["event_id"],
                "batch_id": row["batch_id"],
                "session_id": row["session_id"],
                "source": row["source"],
                "event_type": row["event_type"],
                "timestamp": (row["timestamp"] or row["bucket_start"] or row["received_at"]).isoformat(),
                "metrics": _as_dict(row["metrics"]),
                "dimensions": _as_dict(row["dimensions"]),
            }
            for row in rows
        ],
    }
