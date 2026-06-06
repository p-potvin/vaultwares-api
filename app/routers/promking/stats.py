"""Stats dashboard backing data."""
from __future__ import annotations

from fastapi import APIRouter

from .db import get_pool
from ._models import StatsResponse, FetchRunSummary

router = APIRouter(prefix="/stats", tags=["promking:stats"])


@router.get("", response_model=StatsResponse)
async def stats() -> StatsResponse:
    pool = await get_pool()
    async with pool.acquire() as conn:
        videos_total_rows = await conn.fetch(
            "SELECT site::text AS site, COUNT(*) AS n FROM videos GROUP BY site"
        )
        per_source_rows = await conn.fetch(
            """
            SELECT site::text AS site, source, COUNT(*) AS n
            FROM videos
            GROUP BY site, source
            ORDER BY site, source
            """
        )
        runs_rows = await conn.fetch(
            """
            SELECT id, site::text AS site, source, started_at, finished_at,
                   fetched, added, skipped, errors
            FROM fetch_runs
            ORDER BY started_at DESC
            LIMIT 25
            """
        )

    return StatsResponse(
        videos_total={r["site"]: int(r["n"]) for r in videos_total_rows},
        videos_per_source=[
            {"site": r["site"], "source": r["source"], "n": int(r["n"])}
            for r in per_source_rows
        ],
        fetch_runs_recent=[FetchRunSummary(**dict(r)) for r in runs_rows],
    )
