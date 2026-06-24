from __future__ import annotations

import hashlib
import json
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


def _checksum(event: Dict[str, Any]) -> str:
    payload = {key: value for key, value in event.items() if key != "checksum"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
                else:
                    duplicates += 1
    return {"batch_id": batch["batch_id"], "inserted": inserted, "duplicates": duplicates, "received": len(events)}


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


def _hotspot_top_share(rows: Iterable[Any], clicks: float) -> float:
    hotspots: Dict[str, float] = {}
    for row in rows:
        metrics = _as_dict(row["metrics"])
        for key, value in (metrics.get("click_hotspots") or {}).items():
            hotspots[key] = hotspots.get(key, 0.0) + float(value or 0)
    if not hotspots or clicks <= 0:
        return 0.0
    return max(hotspots.values()) / clicks


def _kpi_signals(
    rows: Iterable[Any],
    totals: Dict[str, float],
    *,
    hours: int,
    latest_received_at: datetime | None,
    generated_at: datetime,
) -> Dict[str, Any]:
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

    best_hour = max(active_by_hour.items(), key=lambda item: item[1])[0] if active_by_hour else None
    best_day = max(active_by_day.items(), key=lambda item: item[1])[0] if active_by_day else None
    expected_minutes = max(1, hours * 60)
    lag_minutes = 0.0
    if latest_received_at:
        lag_minutes = max(0.0, (generated_at - latest_received_at).total_seconds() / 60.0)

    return {
        "focus": {
            "context_switches_per_hour": round(context_switches / max(1.0, hours), 2),
            "avg_focus_minutes_per_switch": round(active_minutes / max(1.0, context_switches), 2),
            "longest_focus_block_minutes": round(_max_metric(rows_list, "longest_focus_streak_seconds") / 60.0, 2),
            "avg_recorded_focus_streak_minutes": round(
                (totals.get("focus_streak_seconds_total", 0.0) / max(1.0, focus_streak_samples)) / 60.0,
                2,
            ),
            "avg_switch_recovery_seconds": round(
                totals.get("switch_recovery_seconds_total", 0.0) / max(1.0, recovery_samples),
                2,
            ),
            "longest_active_block_minutes": round(_max_metric(rows_list, "longest_active_block_seconds") / 60.0, 2),
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
            "hotspot_top_share": round(_hotspot_top_share(rows_list, clicks), 4),
        },
        "rhythm": {
            "best_hour_utc": best_hour,
            "best_day": best_day,
            "active_minutes_per_day": round(active_minutes / max(1.0, len(active_by_day)), 2),
            "avg_rest_gap_minutes": round((totals.get("rest_gap_seconds_total", 0.0) / max(1.0, totals.get("active_starts_after_rest", 0.0))) / 60.0, 2),
            "longest_rest_gap_minutes": round(_max_metric(rows_list, "rest_gap_seconds_max") / 60.0, 2),
        },
        "reliability": {
            "data_coverage_percent": round((len(rows_list) / expected_minutes) * 100.0, 2),
            "missing_minutes_estimate": max(0, expected_minutes - len(rows_list)),
            "batch_lag_minutes": round(lag_minutes, 2),
            "spool_backlog_batches": int(_max_metric(rows_list, "spool_backlog_batches")),
            "spool_backlog_bytes": int(_max_metric(rows_list, "spool_backlog_bytes")),
        },
    }


async def get_input_summary(hours: int = 24) -> Dict[str, Any]:
    if os.environ.get("VW_TELEMETRY_AUTO_SCHEMA", "1") == "1":
        await ensure_schema()
    pool = await get_pool()
    since = datetime.now(timezone.utc) - timedelta(hours=max(1, min(hours, 24 * 14)))
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT event_id, event_type, timestamp, bucket_start, metrics, dimensions, received_at
            FROM input_events
            WHERE COALESCE(bucket_start, timestamp, received_at) >= $1
            ORDER BY COALESCE(bucket_start, timestamp, received_at) DESC
            LIMIT 2000
            """,
            since,
        )
    rows_list = list(rows)
    totals = _sum_numeric_metrics(rows_list)
    latency: Dict[str, float] = {}
    hotspots: Dict[str, float] = {}
    latest = None
    latest_dt = None
    for row in rows_list:
        metrics = _as_dict(row["metrics"])
        if latest is None:
            latest_dt = row["received_at"]
            latest = latest_dt.isoformat() if latest_dt else None
        for key, value in (metrics.get("key_latency_buckets") or {}).items():
            latency[key] = latency.get(key, 0.0) + float(value or 0)
        for key, value in (metrics.get("click_hotspots") or {}).items():
            hotspots[key] = hotspots.get(key, 0.0) + float(value or 0)
    active_minutes = max(1.0, totals.get("active_seconds", 0.0) / 60.0)
    chars = totals.get("chars_typed", 0.0)
    clicks = totals.get("clicks", 0.0)
    travel_m = totals.get("mouse_distance_m", 0.0)
    stale = True
    if latest:
        try:
            stale = datetime.fromisoformat(latest.replace("Z", "+00:00")) < datetime.now(timezone.utc) - timedelta(minutes=10)
        except Exception:
            stale = True
    generated_at = datetime.now(timezone.utc)
    return {
        "source": "vaultwares-api",
        "status": "stale" if stale else "online",
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "latest_received_at": latest,
        "window_hours": hours,
        "totals": {key: round(value, 4) for key, value in totals.items()},
        "derived": {
            "wpm": round((chars / 5.0) / active_minutes, 2),
            "cpm": round(chars / active_minutes, 2),
            "correction_ratio": round((totals.get("backspaces", 0.0) + totals.get("deletes", 0.0)) / max(1.0, chars), 4),
            "click_to_travel_ratio": round(clicks / max(0.001, travel_m), 2),
        },
        "key_latency_buckets": [{"name": key, "count": count} for key, count in sorted(latency.items())],
        "click_hotspots": [{"name": key, "count": count} for key, count in sorted(hotspots.items(), key=lambda item: item[1], reverse=True)[:20]],
        "focus_categories": _bucket_counts(rows_list, "focus_category"),
        "focus_windows": _window_counts(rows_list),
        "kpis": _kpi_signals(rows_list, totals, hours=hours, latest_received_at=latest_dt, generated_at=generated_at),
        "events": [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "timestamp": (row["timestamp"] or row["bucket_start"] or row["received_at"]).isoformat(),
                "metrics": _as_dict(row["metrics"]),
                "dimensions": _as_dict(row["dimensions"]),
            }
            for row in rows_list[:100]
        ],
        "privacy": {
            "raw_text": False,
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
