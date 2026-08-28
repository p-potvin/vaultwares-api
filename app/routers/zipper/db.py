"""Zipper DB — asyncpg pool and schema bootstrap.

Follows the telemetry router's convention: the feature owns its SQL and applies
it idempotently on first pool use, so there is no separate migration step in the
deploy path.

Everything zipper knows lives in Postgres behind the API. That is the point —
site profiles and provider quotas are only correct when centralised, since a
profile learned on one machine should make every other machine's first visit
cheap, and two local quota counters each believe they are at half quota.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None
_schema_ready = False
_ROOT = Path(__file__).resolve().parents[3]
_SCHEMA_SQL = _ROOT / "migrations" / "zipper" / "001_zipper.sql"


def _dsn() -> str:
    dsn = os.environ.get("VW_ZIPPER_DATABASE_URL") or os.environ.get("DB_URL") or ""
    # asyncpg wants postgres://, not postgresql://.
    if dsn.startswith("postgresql://"):
        dsn = "postgres://" + dsn[len("postgresql://"):]
    return dsn


async def _register_json_codecs(conn: asyncpg.Connection) -> None:
    """Decode jsonb to native dict/list instead of leaving it as a string.

    Without this every JSONB column comes back as text and each caller has to
    remember to json.loads it — which is exactly the sort of thing that gets
    forgotten in one place and produces a confusing bug much later.
    """
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename,
            encoder=lambda v: json.dumps(v, ensure_ascii=False, default=str),
            decoder=json.loads,
            schema="pg_catalog",
            format="text",
        )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = _dsn()
        if not dsn:
            raise RuntimeError("VW_ZIPPER_DATABASE_URL or DB_URL is required")
        _pool = await asyncpg.create_pool(
            dsn=dsn, min_size=1, max_size=5, init=_register_json_codecs,
        )
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


async def fetch(query: str, *args) -> list:
    await ensure_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args):
    await ensure_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args) -> str:
    await ensure_schema()
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.execute(query, *args)


def row_to_dict(row) -> Dict[str, Any]:
    if row is None:
        return {}
    out = dict(row)
    # Timestamps go out as ISO strings; the browser has no use for a Python
    # datetime and JSON has no native date.
    for k, v in list(out.items()):
        if hasattr(v, "isoformat"):
            out[k] = v.isoformat()
    return out
