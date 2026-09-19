"""
Prom-King OnlyFans Media Thumbnail Downloader.
Fetches upstream thumbnails (with appropriate referer headers) and persists them locally.
"""
from __future__ import annotations

import logging
from pathlib import Path
import httpx

from .storage import get_video_media_dir, get_media_url

logger = logging.getLogger("promking.media.thumbnail")

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

async def download_and_save_thumbnail(video_id: int, remote_url: str) -> str | None:
    """
    Downloads remote thumbnail image and saves it locally as thumb.jpg.
    Returns the local URL path (/api/promking/media/onlyfans/{video_id}/thumb.jpg).
    """
    if not remote_url or not remote_url.startswith("http"):
        return None

    v_dir = get_video_media_dir(video_id)
    thumb_path = v_dir / "thumb.jpg"

    # If already cached and valid size (> 500 bytes), skip re-download
    if thumb_path.exists() and thumb_path.stat().st_size > 500:
        return get_media_url(video_id, "thumb.jpg")

    headers = {
        "User-Agent": UA,
        "Referer": "https://notfans.com/",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            resp = await client.get(remote_url, headers=headers)
            if resp.status_code != 200:
                logger.warning(
                    "Failed to download thumbnail for video %s from %s: HTTP %s",
                    video_id,
                    remote_url,
                    resp.status_code,
                )
                return None

            data = resp.content
            if len(data) < 500:
                logger.warning("Downloaded thumbnail too small for video %s: %s bytes", video_id, len(data))
                return None

            thumb_path.write_bytes(data)
            logger.info("Saved thumbnail for video %s (%s bytes)", video_id, len(data))
            return get_media_url(video_id, "thumb.jpg")
    except Exception as exc:
        logger.error("Exception downloading thumbnail for video %s: %s", video_id, exc)
        return None
