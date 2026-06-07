from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None
_schema_ready = False


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
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS input_batch_receipts (
              batch_id TEXT PRIMARY KEY,
              session_id TEXT NOT NULL,
              source TEXT NOT NULL,
              schema_version INTEGER NOT NULL,
              host JSONB NOT NULL DEFAULT '{}'::jsonb,
              started_at TIMESTAMPTZ,
              ended_at TIMESTAMPTZ,
              received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              event_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS input_events (
              event_id TEXT PRIMARY KEY,
              batch_id TEXT NOT NULL REFERENCES input_batch_receipts(batch_id) ON DELETE CASCADE,
              session_id TEXT NOT NULL,
              source TEXT NOT NULL,
              event_type TEXT NOT NULL,
              timestamp TIMESTAMPTZ,
              bucket_start TIMESTAMPTZ,
              metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
              dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
              checksum TEXT,
              received_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );

            CREATE INDEX IF NOT EXISTS idx_input_events_bucket_start ON input_events(bucket_start DESC);
            CREATE INDEX IF NOT EXISTS idx_input_events_type ON input_events(event_type);
            CREATE INDEX IF NOT EXISTS idx_input_events_session ON input_events(session_id);

            CREATE TABLE IF NOT EXISTS input_minute_rollups (
              event_id TEXT PRIMARY KEY REFERENCES input_events(event_id) ON DELETE CASCADE,
              bucket_start TIMESTAMPTZ NOT NULL,
              metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
              dimensions JSONB NOT NULL DEFAULT '{}'::jsonb
            );

            CREATE TABLE IF NOT EXISTS input_focus_segments (
              segment_id TEXT PRIMARY KEY,
              batch_id TEXT NOT NULL REFERENCES input_batch_receipts(batch_id) ON DELETE CASCADE,
              started_at TIMESTAMPTZ,
              ended_at TIMESTAMPTZ,
              category TEXT NOT NULL DEFAULT 'unknown',
              window_hash TEXT,
              duration_ms BIGINT NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS input_pointer_hotspots (
              hotspot_id TEXT PRIMARY KEY,
              batch_id TEXT NOT NULL REFERENCES input_batch_receipts(batch_id) ON DELETE CASCADE,
              bucket_start TIMESTAMPTZ,
              x_bucket INTEGER NOT NULL,
              y_bucket INTEGER NOT NULL,
              clicks INTEGER NOT NULL DEFAULT 0,
              scroll_ticks INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS input_ingest_errors (
              id BIGSERIAL PRIMARY KEY,
              batch_id TEXT,
              event_id TEXT,
              error_class TEXT NOT NULL,
              message TEXT NOT NULL,
              payload JSONB,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
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


def _bucket_counts(rows: Iterable[Any], key: str) -> list[dict[str, Any]]:
    counts: Dict[str, float] = {}
    for row in rows:
        metrics = _as_dict(row["metrics"])
        dimensions = _as_dict(row["dimensions"])
        bucket = str(dimensions.get(key) or "unknown")
        counts[bucket] = counts.get(bucket, 0.0) + max(1.0, _num(metrics, "duration_seconds"))
    return [{"name": name, "count": round(count, 2)} for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)]


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
    totals: Dict[str, float] = {}
    latency: Dict[str, float] = {}
    hotspots: Dict[str, float] = {}
    latest = None
    for row in rows:
        metrics = _as_dict(row["metrics"])
        latest = latest or (row["received_at"].isoformat() if row["received_at"] else None)
        for key, value in metrics.items():
            if isinstance(value, (int, float)):
                totals[key] = totals.get(key, 0.0) + float(value)
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
    return {
        "source": "vaultwares-pipelines",
        "status": "stale" if stale else "online",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
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
        "focus_categories": _bucket_counts(rows, "focus_category"),
        "events": [
            {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "timestamp": (row["timestamp"] or row["bucket_start"] or row["received_at"]).isoformat(),
                "metrics": _as_dict(row["metrics"]),
                "dimensions": _as_dict(row["dimensions"]),
            }
            for row in rows[:100]
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
