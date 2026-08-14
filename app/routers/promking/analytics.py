from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from .db import get_pool
from ._models import (
    SearchLogRequest,
    AdClickRequest,
    VideoReactionRequest,
    VideoPlayRequest,
    PostbackRequest,
)

router = APIRouter(prefix="/analytics", tags=["promking:analytics"])


@router.post("/search/log")
async def log_search(payload: SearchLogRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO search_logs (site, query, results_count)
            VALUES ($1, $2, $3)
            """,
            payload.site,
            payload.query,
            payload.results_count,
        )
    return {"ok": True}


@router.post("/ads/click")
async def log_ad_click(payload: AdClickRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO ad_clicks (site, ad_id, placement)
            VALUES ($1, $2, $3)
            """,
            payload.site,
            payload.ad_id,
            payload.placement,
        )
    return {"ok": True}


@router.get("/videos/{video_id}/reaction")
async def get_video_reaction_stats(video_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) FILTER (WHERE reaction_type = 'like') AS likes,
                COUNT(*) FILTER (WHERE reaction_type = 'dislike') AS dislikes
            FROM video_reactions
            WHERE video_id = $1
            """,
            video_id,
        )
    return {
        "likes": int(row["likes"] or 0) if row else 0,
        "dislikes": int(row["dislikes"] or 0) if row else 0,
    }


@router.post("/videos/{video_id}/reaction")
async def record_video_reaction(video_id: int, payload: VideoReactionRequest):
    pool = await get_pool()
    reaction_type = payload.reaction_type.lower()
    if reaction_type not in ("like", "dislike"):
        raise HTTPException(status_code=400, detail="Reaction must be 'like' or 'dislike'")

    async with pool.acquire() as conn:
        # Verify video exists
        v = await conn.fetchval("SELECT id FROM videos WHERE id = $1", video_id)
        if not v:
            raise HTTPException(status_code=404, detail="Video not found")

        if payload.user_id:
            # Check unique by user_id
            existing_id = await conn.fetchval(
                "SELECT id FROM video_reactions WHERE video_id = $1 AND user_id = $2",
                video_id,
                payload.user_id,
            )
            if existing_id:
                await conn.execute(
                    "UPDATE video_reactions SET reaction_type = $2, created_at = now() WHERE id = $1",
                    existing_id,
                    reaction_type,
                )
            else:
                await conn.execute(
                    "INSERT INTO video_reactions (video_id, user_id, reaction_type) VALUES ($1, $2, $3)",
                    video_id,
                    payload.user_id,
                    reaction_type,
                )
        elif payload.anon_id:
            # Check unique by anon_id
            existing_id = await conn.fetchval(
                "SELECT id FROM video_reactions WHERE video_id = $1 AND anon_id = $2",
                video_id,
                payload.anon_id,
            )
            if existing_id:
                await conn.execute(
                    "UPDATE video_reactions SET reaction_type = $2, created_at = now() WHERE id = $1",
                    existing_id,
                    reaction_type,
                )
            else:
                await conn.execute(
                    "INSERT INTO video_reactions (video_id, anon_id, reaction_type) VALUES ($1, $2, $3)",
                    video_id,
                    payload.anon_id,
                    reaction_type,
                )
        else:
            # Guest click with no identifiers
            await conn.execute(
                "INSERT INTO video_reactions (video_id, reaction_type) VALUES ($1, $2)",
                video_id,
                reaction_type,
            )

        # Get updated stats
        likes = await conn.fetchval(
            "SELECT COUNT(*) FROM video_reactions WHERE video_id = $1 AND reaction_type = 'like'",
            video_id,
        )
        dislikes = await conn.fetchval(
            "SELECT COUNT(*) FROM video_reactions WHERE video_id = $1 AND reaction_type = 'dislike'",
            video_id,
        )

    return {
        "ok": True,
        "likes": int(likes or 0),
        "dislikes": int(dislikes or 0),
    }


@router.post("/videos/{video_id}/play")
async def record_video_play(video_id: int, payload: VideoPlayRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Verify video exists
        v = await conn.fetchval("SELECT id FROM videos WHERE id = $1", video_id)
        if not v:
            raise HTTPException(status_code=404, detail="Video not found")

        await conn.execute(
            """
            INSERT INTO video_plays (video_id, site, anon_id, user_id, duration_watched, completed)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            video_id,
            payload.site,
            payload.anon_id,
            payload.user_id,
            payload.duration_watched,
            payload.completed,
        )
    return {"ok": True}


@router.post("/postback")
async def log_postback(payload: PostbackRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO postbacks (site, offer_id, offer_name, aff_click_id, transaction_id, payout, currency, source, ip, ran, raw_params)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            """,
            payload.site,
            payload.offer_id,
            payload.offer_name,
            payload.aff_click_id,
            payload.transaction_id,
            payload.payout,
            payload.currency,
            payload.source,
            payload.ip,
            payload.ran,
            payload.raw_params,
        )
    return {"ok": True}
