#!/usr/bin/env python3
"""Apply VaultWares API telemetry migrations to Postgres."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "migrations" / "telemetry"


def _dsn() -> str:
    load_dotenv(ROOT / ".env")
    dsn = os.environ.get("VW_TELEMETRY_DATABASE_URL") or os.environ.get("DB_URL") or ""
    if dsn.startswith("postgresql://"):
        dsn = "postgres://" + dsn[len("postgresql://") :]
    if not dsn:
        raise SystemExit("VW_TELEMETRY_DATABASE_URL or DB_URL is required")
    return dsn


async def main() -> int:
    conn = await asyncpg.connect(dsn=_dsn())
    try:
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            await conn.execute(migration.read_text(encoding="utf-8"))
            print(f"applied {migration.relative_to(ROOT)}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
