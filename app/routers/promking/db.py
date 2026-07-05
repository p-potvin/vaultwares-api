"""
Promking DB — asyncpg pool.

We deliberately do NOT mirror the Drizzle schema in SQLAlchemy/Tortoise. The
authoritative schema lives in `Prom-King/shared-tube/shared/src/db/schema.ts`;
migrations are run via `drizzle-kit migrate`. FastAPI treats the DB as a
query target with parameterized SQL.

PROMKING_DATABASE_URL env var is required (e.g.
postgres://postgres:postgres@localhost:5432/promking).

Codecs: we register a JSON/JSONB codec on every connection so `settings.value`,
`fetch_runs.log`, `videos.qualities`, etc. come back as native Python objects
instead of raw JSON strings. Without this asyncpg returns jsonb as `str`, and
the Astro Layout + admin Settings tab both do
`typeof x === 'object' ? … : {}` on the response — a jsonb string flips to
false and every marketing snippet silently vanishes. See fix note on
2026-07-05 (Marketing tab snippets never rendered on the live sites).
"""
from __future__ import annotations

import json
import os
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


async def _register_json_codecs(conn: asyncpg.Connection) -> None:
    """
    Register the same codec for `json` and `jsonb` on the connection so
    reads decode to Python objects and writes accept dicts/lists directly.
    """
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = os.environ.get("PROMKING_DATABASE_URL")
        if not dsn:
            raise RuntimeError(
                "PROMKING_DATABASE_URL is not set. See "
                "Prom-King/shared-tube/docs/postgres.md for the local default."
            )
        # asyncpg uses postgres:// not postgresql:// — normalise.
        if dsn.startswith("postgresql://"):
            dsn = "postgres://" + dsn[len("postgresql://"):]
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=10,
            init=_register_json_codecs,
        )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
