"""
Prom-King OnlyFans Media Processing Pipeline.
Coordinates thumbnail downloading, animated preview generation, and sprite sheet
creation exclusively for OnlyFans videos.
"""
from __future__ import annotations

import logging
from typing import Any
import asyncpg

from ..db import get_pool
from .thumbnail import download_and_save_thumbnail
from .generator import probe_video_duration, generate_animated_preview, generate_sprite_sheet
from .db import upsert_onlyfans_media, sync_video_media_urls, get_onlyfans_media

logger = logging.getLogger("promking.media.processor")


def _find_best_mp4_url(qualities: Any, embed_url: str | None) -> str | None:
    """Finds a direct MP4 streaming URL from qualities or embed_url."""
    if isinstance(qualities, list):
        for q in qualities:
            if isinstance(q, dict):
                url = q.get("url") or ""
                if url.startswith("http") and (".mp4" in url or "/get_file/" in url):
                    return url
    if embed_url and embed_url.startswith("http") and (".mp4" in embed_url or "/get_file/" in embed_url):
        return embed_url
    return None


async def _refresh_notfans_mp4_url(source_url: str | None) -> str | None:
    """Re-fetches the NotFans video page to obtain a fresh, non-expired MP4 token."""
    if not source_url or "notfans.com/videos/" not in source_url:
        return None
    try:
        import httpx
        import re
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(source_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                matches = re.findall(r'href=[\'"]([^\'"]*get_file[^\'"]*\.mp4[^\'"]*)[\'"]', resp.text)
                if matches:
                    return matches[0]
    except Exception as exc:
        logger.warning("Failed to refresh NotFans MP4 URL for %s: %s", source_url, exc)
    return None


async def process_onlyfans_media(
    video_id: int,
    video_data: dict[str, Any],
    pool: asyncpg.Pool | None = None,
) -> dict[str, Any] | None:
    """
    Main entrypoint for processing OnlyFans media assets for a given video.
    Strictly scoped to OnlyFans videos.
    """
    is_of = bool(
        video_data.get("isOnlyfans")
        or video_data.get("is_onlyfans")
        or video_data.get("source") == "notfans"
    )
    if not is_of:
        logger.debug("Skipping media processing for non-OnlyFans video %s", video_id)
        return None

    if pool is None:
        pool = await get_pool()

    # 1. Download and save thumbnail
    remote_thumb = (
        video_data.get("thumbnailUrl")
        or video_data.get("thumbnail_url")
        or video_data.get("previewUrl")
        or video_data.get("preview_url")
    )
    local_thumb_url: str | None = None
    if remote_thumb and isinstance(remote_thumb, str) and remote_thumb.startswith("http"):
        local_thumb_url = await download_and_save_thumbnail(video_id, remote_thumb)
    elif remote_thumb and isinstance(remote_thumb, str) and remote_thumb.startswith("/api/promking/media/"):
        local_thumb_url = remote_thumb

    # 2. Locate source video stream
    qualities = video_data.get("qualities")
    embed_url = video_data.get("embedUrl") or video_data.get("embed_url")
    source_url = video_data.get("sourceUrl") or video_data.get("source_url")
    mp4_url = _find_best_mp4_url(qualities, embed_url)

    # 3. Determine duration
    duration = float(video_data.get("durationSeconds") or video_data.get("duration_seconds") or 0.0)
    if duration <= 0 and mp4_url:
        probed = await probe_video_duration(mp4_url)
        if probed and probed > 0:
            duration = probed
        else:
            # Token might have expired (410), refresh from source_url
            fresh_url = await _refresh_notfans_mp4_url(source_url)
            if fresh_url:
                mp4_url = fresh_url
                probed = await probe_video_duration(mp4_url)
                if probed and probed > 0:
                    duration = probed

    preview_video_url: str | None = None
    sprite_url: str | None = None
    sprite_vtt_url: str | None = None
    sprite_meta: dict[str, Any] = {
        "tile_width": 160,
        "tile_height": 90,
        "tile_count": 30,
        "tiles_per_row": 6,
        "interval_seconds": 0.0,
    }

    # 4. Generate 30-frame sprite sheet for hover animation and timeline scrubbing
    if mp4_url:
        sprite_url, sprite_vtt_url, sprite_meta = await generate_sprite_sheet(
            video_id,
            mp4_url,
            duration,
            tile_count=30,
            tiles_per_row=6,
            tile_width=160,
            tile_height=90,
        )
        if not sprite_url:
            # Token might have expired, attempt refresh
            fresh_url = await _refresh_notfans_mp4_url(source_url)
            if fresh_url and fresh_url != mp4_url:
                mp4_url = fresh_url
                sprite_url, sprite_vtt_url, sprite_meta = await generate_sprite_sheet(
                    video_id,
                    mp4_url,
                    duration,
                    tile_count=30,
                    tiles_per_row=6,
                    tile_width=160,
                    tile_height=90,
                )

    # 5. Persist to onlyfans_media association table
    async with pool.acquire() as conn:
        media_row = await upsert_onlyfans_media(
            conn=conn,
            video_id=video_id,
            thumbnail_url=local_thumb_url,
            preview_video_url=preview_video_url,
            sprite_url=sprite_url,
            sprite_vtt_url=sprite_vtt_url,
            tile_width=sprite_meta["tile_width"],
            tile_height=sprite_meta["tile_height"],
            tile_count=sprite_meta["tile_count"],
            tiles_per_row=sprite_meta["tiles_per_row"],
            interval_seconds=sprite_meta["interval_seconds"],
        )

        # 6. Synchronize videos row with local thumbnail and preview URLs
        await sync_video_media_urls(
            conn=conn,
            video_id=video_id,
            thumbnail_url=local_thumb_url,
            preview_url=preview_video_url,
            duration_seconds=int(duration) if duration > 0 else None,
        )

    logger.info(
        "Successfully processed OnlyFans media for video %s: thumb=%s, preview=%s, sprite=%s",
        video_id,
        bool(local_thumb_url),
        bool(preview_video_url),
        bool(sprite_url),
    )
    return media_row
