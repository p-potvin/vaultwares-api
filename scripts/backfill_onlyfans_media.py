"""
Backfill script for Prom-King OnlyFans Media.
Generates local thumbnails, 30-frame sprite sheets, and WebVTT scrubbing tracks
for existing OnlyFans videos in the database.
"""
import sys
import os
import asyncio
import logging
from pathlib import Path

# Add the parent directory to sys.path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app.routers.promking.db import get_pool
from app.routers.promking.media import process_onlyfans_media

sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("backfill_onlyfans_media")


async def backfill_onlyfans_videos(concurrency: int = 2, force: bool = False):
    pool = await get_pool()
    async with pool.acquire() as conn:
        if force:
            sql = """
                SELECT id, title, slug, source, source_url, embed_url, qualities,
                       thumbnail_url, preview_url, duration_seconds, is_onlyfans
                FROM videos
                WHERE is_onlyfans = true
                ORDER BY id DESC
            """
        else:
            sql = """
                SELECT v.id, v.title, v.slug, v.source, v.source_url, v.embed_url, v.qualities,
                       v.thumbnail_url, v.preview_url, v.duration_seconds, v.is_onlyfans
                FROM videos v
                LEFT JOIN onlyfans_media om ON om.video_id = v.id
                WHERE v.is_onlyfans = true
                  AND (om.sprite_url IS NULL OR om.sprite_url = '')
                ORDER BY v.id DESC
            """
        rows = await conn.fetch(sql)

    total = len(rows)
    logger.info("Found %d OnlyFans videos needing media backfill.", total)
    if total == 0:
        logger.info("All OnlyFans videos already have sprite sheets generated.")
        return

    sem = asyncio.Semaphore(concurrency)
    processed = 0
    succeeded = 0
    failed = 0
    lock = asyncio.Lock()

    async def process_one(idx: int, r):
        nonlocal processed, succeeded, failed
        video_id = r["id"]
        title = r["title"] or r["slug"]
        v_data = {
            "is_onlyfans": True,
            "title": title,
            "source": r["source"],
            "source_url": r["source_url"],
            "embed_url": r["embed_url"],
            "qualities": r["qualities"],
            "thumbnail_url": r["thumbnail_url"],
            "preview_url": r["preview_url"],
            "duration_seconds": r["duration_seconds"],
        }

        async with sem:
            logger.info("[%d/%d] Starting processing for Video #%d: '%s'", idx, total, video_id, title[:50])
            try:
                res = await process_onlyfans_media(video_id, v_data, pool=pool)
                async with lock:
                    processed += 1
                    if res and res.get("sprite_url"):
                        succeeded += 1
                        logger.info(
                            "[%d/%d] Video #%d SUCCESS: sprite=%s, thumb=%s",
                            processed, total, video_id, res.get("sprite_url"), res.get("thumbnail_url"),
                        )
                    else:
                        succeeded += 1
                        logger.info(
                            "[%d/%d] Video #%d PARTIAL: thumb=%s (sprite could not be generated)",
                            processed, total, video_id, res.get("thumbnail_url") if res else None,
                        )
            except Exception as exc:
                async with lock:
                    processed += 1
                    failed += 1
                logger.error("[%d/%d] Video #%d FAILED: %s", processed, total, video_id, exc)

    tasks = [asyncio.create_task(process_one(i + 1, r)) for i, r in enumerate(rows)]
    await asyncio.gather(*tasks)

    logger.info("--- BACKFILL COMPLETE ---")
    logger.info("Total: %d | Succeeded: %d | Failed: %d", total, succeeded, failed)


if __name__ == "__main__":
    concurrency = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    force = "--force" in sys.argv
    asyncio.run(backfill_onlyfans_videos(concurrency=concurrency, force=force))
