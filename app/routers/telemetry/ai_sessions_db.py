"""Persistence for AI assistant session telemetry.

Reuses the telemetry connection pool from .db so the API keeps a single
Postgres pool. The API stays the only service that touches the database;
collectors on each host ship NDJSON spool batches to the ingest endpoint.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db import get_pool

_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_SQL = _ROOT / "migrations" / "telemetry" / "003_ai_sessions.sql"
_schema_ready = False

# Columns written straight through; anything else on a record lands in `extra`.
_KNOWN = {
    "tool", "host", "session_id", "title", "project", "cwd", "model",
    "started_at", "last_activity_at", "message_count", "user_message_count",
    "tokens_used", "input_tokens", "output_tokens", "cached_input_tokens",
    "reasoning_tokens", "archived", "git_branch", "source_path", "size_bytes",
    "parser",
}


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


def batch_id_for(host: str, collected_at: Any, batch_index: Any) -> str:
    """Deterministic id so a retried spool file cannot double-insert.

    drain-ai-sessions.ps1 restarts a file from its first line after a failure,
    so the same batch is re-POSTed; hashing the identity makes that a no-op.
    """
    raw = f"{host}|{collected_at}|{batch_index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


async def store_session_batch(batch: Dict[str, Any]) -> Dict[str, Any]:
    await ensure_schema()

    host = str(batch.get("host") or "unknown")
    collected_at = _coerce_dt(batch.get("collectedAt") or batch.get("collected_at"))
    batch_index = _as_int(batch.get("batchIndex") or batch.get("batch_index")) or 0
    sessions: List[Dict[str, Any]] = batch.get("sessions") or []
    bid = batch_id_for(host, batch.get("collectedAt") or batch.get("collected_at"), batch_index)

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO ai_session_batch_receipts
                    (batch_id, source, schema_version, host, batch_index,
                     collected_at, session_count)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (batch_id) DO UPDATE
                    SET session_count = EXCLUDED.session_count,
                        received_at = now()
                """,
                bid,
                str(batch.get("source") or "vw-ai-sessions"),
                _as_int(batch.get("schema")) or 1,
                host,
                batch_index,
                collected_at,
                len(sessions),
            )

            rows = []
            for s in sessions:
                extra = {k: v for k, v in s.items() if k not in _KNOWN and v is not None}
                rows.append((
                    str(s.get("host") or host),
                    str(s.get("tool") or "unknown"),
                    str(s.get("session_id") or ""),
                    bid,
                    s.get("title"),
                    s.get("project"),
                    s.get("cwd"),
                    s.get("model"),
                    _coerce_dt(s.get("started_at")),
                    _coerce_dt(s.get("last_activity_at")),
                    _as_int(s.get("message_count")),
                    _as_int(s.get("user_message_count")),
                    _as_int(s.get("tokens_used")),
                    _as_int(s.get("input_tokens")),
                    _as_int(s.get("output_tokens")),
                    _as_int(s.get("cached_input_tokens")),
                    _as_int(s.get("reasoning_tokens")),
                    s.get("archived"),
                    s.get("git_branch"),
                    s.get("source_path"),
                    _as_int(s.get("size_bytes")),
                    str(s.get("parser") or "full"),
                    json.dumps(extra, default=str),
                ))

            if rows:
                await conn.executemany(
                    """
                    INSERT INTO ai_sessions (
                        host, tool, session_id, batch_id, title, project, cwd, model,
                        started_at, last_activity_at, message_count, user_message_count,
                        tokens_used, input_tokens, output_tokens, cached_input_tokens,
                        reasoning_tokens, archived, git_branch, source_path, size_bytes,
                        parser, extra
                    ) VALUES (
                        $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,
                        $18,$19,$20,$21,$22,$23::jsonb
                    )
                    ON CONFLICT (host, tool, session_id) DO UPDATE SET
                        batch_id = EXCLUDED.batch_id,
                        title = COALESCE(EXCLUDED.title, ai_sessions.title),
                        project = COALESCE(EXCLUDED.project, ai_sessions.project),
                        cwd = COALESCE(EXCLUDED.cwd, ai_sessions.cwd),
                        model = COALESCE(EXCLUDED.model, ai_sessions.model),
                        started_at = LEAST(
                            COALESCE(EXCLUDED.started_at, ai_sessions.started_at),
                            COALESCE(ai_sessions.started_at, EXCLUDED.started_at)),
                        last_activity_at = GREATEST(
                            COALESCE(EXCLUDED.last_activity_at, ai_sessions.last_activity_at),
                            COALESCE(ai_sessions.last_activity_at, EXCLUDED.last_activity_at)),
                        message_count = GREATEST(
                            COALESCE(EXCLUDED.message_count, 0),
                            COALESCE(ai_sessions.message_count, 0)),
                        user_message_count = GREATEST(
                            COALESCE(EXCLUDED.user_message_count, 0),
                            COALESCE(ai_sessions.user_message_count, 0)),
                        tokens_used = GREATEST(
                            COALESCE(EXCLUDED.tokens_used, 0),
                            COALESCE(ai_sessions.tokens_used, 0)),
                        input_tokens = COALESCE(EXCLUDED.input_tokens, ai_sessions.input_tokens),
                        output_tokens = COALESCE(EXCLUDED.output_tokens, ai_sessions.output_tokens),
                        cached_input_tokens = COALESCE(EXCLUDED.cached_input_tokens,
                                                       ai_sessions.cached_input_tokens),
                        reasoning_tokens = COALESCE(EXCLUDED.reasoning_tokens,
                                                    ai_sessions.reasoning_tokens),
                        archived = COALESCE(EXCLUDED.archived, ai_sessions.archived),
                        git_branch = COALESCE(EXCLUDED.git_branch, ai_sessions.git_branch),
                        source_path = COALESCE(EXCLUDED.source_path, ai_sessions.source_path),
                        size_bytes = COALESCE(EXCLUDED.size_bytes, ai_sessions.size_bytes),
                        parser = EXCLUDED.parser,
                        extra = ai_sessions.extra || EXCLUDED.extra,
                        updated_at = now()
                    """,
                    rows,
                )

    return {"batch_id": bid, "stored": len(rows)}


# --------------------------------------------------------------- read side


async def get_summary(days: Optional[int] = None) -> Dict[str, Any]:
    await ensure_schema()
    where, params = _window(days)
    pool = await get_pool()
    async with pool.acquire() as conn:
        totals = await conn.fetchrow(
            f"""
            SELECT count(*) AS sessions,
                   COALESCE(sum(message_count), 0) AS messages,
                   COALESCE(sum(tokens_used), 0) AS tokens,
                   COALESCE(sum(size_bytes), 0) AS bytes,
                   count(*) FILTER (WHERE parser <> 'full') AS metadata_only,
                   min(started_at) AS earliest,
                   max(last_activity_at) AS latest
            FROM ai_sessions {where}
            """,
            *params,
        )
        by_tool = await conn.fetch(
            f"""
            SELECT tool,
                   count(*) AS sessions,
                   COALESCE(sum(message_count), 0) AS messages,
                   COALESCE(sum(tokens_used), 0) AS tokens,
                   count(*) FILTER (WHERE parser <> 'full') AS metadata_only,
                   max(last_activity_at) AS latest
            FROM ai_sessions {where}
            GROUP BY tool ORDER BY sessions DESC
            """,
            *params,
        )
        by_host = await conn.fetch(
            f"SELECT host, count(*) AS sessions FROM ai_sessions {where} "
            "GROUP BY host ORDER BY sessions DESC",
            *params,
        )
        model_clause = (
            f"{where} AND model IS NOT NULL" if where else "WHERE model IS NOT NULL"
        )
        by_model = await conn.fetch(
            f"SELECT model, count(*) AS sessions FROM ai_sessions {model_clause} "
            "GROUP BY model ORDER BY sessions DESC LIMIT 25",
            *params,
        )

    return {
        "totals": dict(totals) if totals else {},
        "by_tool": [dict(r) for r in by_tool],
        "by_host": [dict(r) for r in by_host],
        "by_model": [dict(r) for r in by_model],
    }


def _window(days: Optional[int]):
    if days:
        return "WHERE last_activity_at >= now() - ($1 || ' days')::interval", [str(days)]
    return "", []


async def get_projects(limit: int = 50, days: Optional[int] = None) -> Dict[str, Any]:
    await ensure_schema()
    where, params = _window(days)
    clause = f"{where} AND project IS NOT NULL" if where else "WHERE project IS NOT NULL"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT lower(project) AS project,
                   count(*) AS sessions,
                   count(DISTINCT tool) AS tools,
                   COALESCE(sum(message_count), 0) AS messages,
                   COALESCE(sum(tokens_used), 0) AS tokens,
                   max(last_activity_at) AS latest
            FROM ai_sessions {clause}
            GROUP BY lower(project)
            ORDER BY sessions DESC
            LIMIT {int(limit)}
            """,
            *params,
        )
    return {"projects": [dict(r) for r in rows]}


async def get_timeline(bucket: str = "day", days: int = 90) -> Dict[str, Any]:
    await ensure_schema()
    trunc = bucket if bucket in ("day", "week", "month") else "day"
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT date_trunc('{trunc}', COALESCE(started_at, last_activity_at)) AS bucket,
                   tool,
                   count(*) AS sessions,
                   COALESCE(sum(message_count), 0) AS messages,
                   COALESCE(sum(tokens_used), 0) AS tokens
            FROM ai_sessions
            WHERE COALESCE(started_at, last_activity_at) >= now() - ($1 || ' days')::interval
            GROUP BY 1, 2
            ORDER BY 1 ASC
            """,
            str(days),
        )
    return {"bucket": trunc, "days": days, "points": [dict(r) for r in rows]}


async def search_sessions(
    q: str = "",
    tool: Optional[str] = None,
    host: Optional[str] = None,
    project: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    await ensure_schema()
    clauses: List[str] = []
    params: List[Any] = []

    if q:
        params.append(f"%{q.lower()}%")
        clauses.append(f"(lower(title) LIKE ${len(params)} OR lower(cwd) LIKE ${len(params)})")
    for column, value in (("tool", tool), ("host", host)):
        if value:
            params.append(value)
            clauses.append(f"{column} = ${len(params)}")
    if project:
        params.append(project.lower())
        clauses.append(f"lower(project) = ${len(params)}")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT host, tool, session_id, title, project, model,
                   started_at, last_activity_at, message_count, tokens_used,
                   archived, parser
            FROM ai_sessions {where}
            ORDER BY last_activity_at DESC NULLS LAST
            LIMIT {int(limit)}
            """,
            *params,
        )
    return {"count": len(rows), "sessions": [dict(r) for r in rows]}
