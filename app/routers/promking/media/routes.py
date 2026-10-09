"""
Prom-King OnlyFans Media HTTP Routes.
Serves static media files (thumbnails, preview clips, sprite sheets, VTTs)
and exposes an on-demand generation endpoint.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse

from ..db import get_pool
from ..fetcher import _shared_tube_path
from .storage import get_media_file_path
from .processor import process_onlyfans_media
from .db import get_onlyfans_media

logger = logging.getLogger("promking.media.routes")

router = APIRouter(tags=["promking-media"])


@router.api_route("/media/onlyfans/{video_id}/{filename}", methods=["GET", "HEAD"])
async def serve_onlyfans_media(
    video_id: int,
    filename: str,
    request: Request,
):
    """
    Serves cached OnlyFans media files directly from local storage.
    Supports HTTP Range requests for video clips and sends 30-day immutable cache headers.
    """
    file_path = get_media_file_path(video_id, filename)
    if not file_path or not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="Media file not found")

    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        if filename.endswith(".vtt"):
            content_type = "text/vtt; charset=utf-8"
        elif filename.endswith(".mp4"):
            content_type = "video/mp4"
        elif filename.endswith(".jpg") or filename.endswith(".jpeg"):
            content_type = "image/jpeg"
        elif filename.endswith(".webp"):
            content_type = "image/webp"
        else:
            content_type = "application/octet-stream"

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    headers = {
        "Content-Type": content_type,
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=2592000, immutable",  # 30 days
    }

    # Handle Range requests for video streaming
    if range_header and range_header.startswith("bytes="):
        range_val = range_header[6:].strip()
        parts = range_val.split("-")
        try:
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
            if start >= file_size or end >= file_size or start > end:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

            chunk_length = end - start + 1

            def iterfile():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_length
                    while remaining > 0:
                        chunk = f.read(min(remaining, 64 * 1024))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(chunk_length)
            return StreamingResponse(iterfile(), status_code=206, headers=headers)
        except Exception as exc:
            logger.warning("Error processing range header for %s: %s", file_path, exc)

    headers["Content-Length"] = str(file_size)
    return FileResponse(file_path, media_type=content_type, headers=headers)


@router.post("/media/onlyfans/{video_id}/generate")
async def trigger_generate_onlyfans_media(
    video_id: int,
):
    """
    On-demand endpoint to generate/backfill media assets for a specific OnlyFans video.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        video_row = await conn.fetchrow(
            "SELECT * FROM videos WHERE id = $1",
            video_id,
        )
        if not video_row:
            raise HTTPException(status_code=404, detail="Video not found")

        v_dict = dict(video_row)
        if not v_dict.get("is_onlyfans") and v_dict.get("source") != "notfans":
            raise HTTPException(status_code=400, detail="Video is not an OnlyFans video")

    res = await process_onlyfans_media(video_id, v_dict, pool=pool)
    if not res:
        raise HTTPException(status_code=500, detail="Media generation failed")

    return {"ok": True, "media": res}


@router.get("/media/onlyfans/{video_id}")
async def get_video_onlyfans_media(
    video_id: int,
):
    """
    Returns the onlyfans_media metadata record for a video if present.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        media = await get_onlyfans_media(conn, video_id)
        if not media:
            raise HTTPException(status_code=404, detail="No OnlyFans media record found for video")
        return media


@router.api_route("/media/cache/{media_hash}", methods=["GET", "HEAD"])
async def serve_cached_media(
    media_hash: str,
    request: Request,
):
    """
    Serves cached media assets (such as audio-enabled preview clips) directly from OVH local storage.
    Supports HTTP Range requests for video streaming and sends 30-day immutable cache headers.
    """
    clean_hash = media_hash.split(".")[0].strip().lower()
    if not re.match(r"^[a-f0-9]{64}$", clean_hash):
        raise HTTPException(status_code=400, detail="Invalid media hash format")

    shared_tube = _shared_tube_path()
    file_path = shared_tube / "data" / "media" / clean_hash
    meta_path = shared_tube / "data" / "media" / f"{clean_hash}.meta"

    if not file_path.exists() or not file_path.is_file():
        # Fallback: check if the file was stored under sha256(clean_hash) due to legacy double-hashing
        import hashlib
        alt_hash = hashlib.sha256(clean_hash.encode("utf-8")).hexdigest()
        alt_path = shared_tube / "data" / "media" / alt_hash
        if alt_path.exists() and alt_path.is_file():
            file_path = alt_path
            meta_path = shared_tube / "data" / "media" / f"{alt_hash}.meta"
        else:
            raise HTTPException(status_code=404, detail="Cached media file not found")

    content_type = "video/mp4"
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                if meta.get("contentType"):
                    content_type = meta["contentType"]
        except Exception:
            pass

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    headers = {
        "Content-Type": content_type,
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=2592000, immutable",
    }

    if range_header and range_header.startswith("bytes="):
        range_val = range_header[6:].strip()
        parts = range_val.split("-")
        try:
            start = int(parts[0]) if parts[0] else 0
            end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1
            if start >= file_size or end >= file_size or start > end:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})

            chunk_length = end - start + 1

            def iterfile():
                with open(file_path, "rb") as f:
                    f.seek(start)
                    remaining = chunk_length
                    while remaining > 0:
                        chunk = f.read(min(remaining, 64 * 1024))
                        if not chunk:
                            break
                        remaining -= len(chunk)
                        yield chunk

            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
            headers["Content-Length"] = str(chunk_length)
            return StreamingResponse(iterfile(), status_code=206, headers=headers)
        except Exception as exc:
            logger.warning("Error processing range header for %s: %s", file_path, exc)

    headers["Content-Length"] = str(file_size)
    return FileResponse(file_path, media_type=content_type, headers=headers)
