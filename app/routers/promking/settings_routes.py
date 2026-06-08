"""Per-site settings (JSONB)."""
from __future__ import annotations

import json

from fastapi import APIRouter, Path

from .db import get_pool
from ._models import Site, SettingsPayload

router = APIRouter(prefix="/settings", tags=["promking:settings"])


@router.get("/{site}", response_model=dict)
async def get_settings(site: Site = Path(...)) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value FROM settings WHERE site = $1",
            site,
        )
    return {r["key"]: r["value"] for r in rows}


@router.put("/{site}", response_model=dict)
async def put_settings(payload: SettingsPayload, site: Site = Path(...)) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        for key, value in payload.values.items():
            await conn.execute(
                """
                INSERT INTO settings (site, key, value, updated_at)
                VALUES ($1, $2, $3::jsonb, NOW())
                ON CONFLICT (site, key) DO UPDATE
                  SET value = EXCLUDED.value,
                      updated_at = NOW()
                """,
                site,
                key,
                json.dumps(value),
            )
    return {"ok": True, "updated_keys": list(payload.values.keys())}
