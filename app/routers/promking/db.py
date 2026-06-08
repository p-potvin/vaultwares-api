"""
Promking DB — asyncpg pool.

We deliberately do NOT mirror the Drizzle schema in SQLAlchemy/Tortoise. The
authoritative schema lives in `Prom-King/shared-tube/shared/src/db/schema.ts`;
migrations are run via `drizzle-kit migrate`. FastAPI treats the DB as a
query target with parameterized SQL.

PROMKING_DATABASE_URL env var is required (e.g.
postgres://postgres:postgres@localhost:5432/promking).
"""
from __future__ import annotations

import os
from typing import Optional

import asyncpg

_pool: Optional[asyncpg.Pool] = None


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
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
