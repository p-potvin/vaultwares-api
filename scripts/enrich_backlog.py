import sys
import os
import asyncio
import argparse
import logging
from pathlib import Path

# Add the parent directory to sys.path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.routers.promking.db import get_pool
from app.routers.promking.fetcher import _attach_terms
from app.routers.promking.tpdb import fetch_tpdb_tags

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("enrich_backlog")

async def clear_terms(conn, video_id: int):
    await conn.execute("DELETE FROM video_pornstars WHERE video_id = $1", video_id)
    await conn.execute("DELETE FROM video_categories WHERE video_id = $1", video_id)
    await conn.execute("DELETE FROM video_studios WHERE video_id = $1", video_id)

async def enrich_backlog(limit: int = 1000, site: str = "sexyprn", start_id: int = 0):
    logger.info(f"Connecting to database to enrich {limit} videos for {site}...")
    pool = await get_pool()
    
    async with pool.acquire() as conn:
        # Fetch videos that need enrichment
        rows = await conn.fetch(
            """
            SELECT id, title
            FROM videos
            WHERE site = $1 AND id > $2
            ORDER BY id ASC
            LIMIT $3
            """,
            site,
            start_id,
            limit
        )
        
        if not rows:
            logger.info("No more videos to enrich.")
            return

        logger.info(f"Loaded {len(rows)} videos. Processing...")
        
        matches = 0
        for index, row in enumerate(rows):
            video_id = row["id"]
            title = row["title"]
            
            if not title:
                continue
                
            logger.info(f"[{index + 1}/{len(rows)}] Video #{video_id}: '{title}'")
            
            tpdb_data = await fetch_tpdb_tags(title)
            
            if tpdb_data:
                matches += 1
                logger.info(f"  -> MATCHED! Found {len(tpdb_data['categories'])} categories, {len(tpdb_data['performers'])} performers.")
                
                # Delete old tags
                await clear_terms(conn, video_id)
                
                # Attach new curated tags
                v = {
                    "categories": tpdb_data["categories"],
                    "actors": tpdb_data["performers"],
                    "studios": tpdb_data["studios"],
                }
                
                try:
                    await _attach_terms(conn, video_id, v)
                except Exception as e:
                    logger.error(f"  -> Error attaching terms for video {video_id}: {e}")
            else:
                logger.info("  -> NO MATCH")
                
        logger.info(f"Finished batch. Matched {matches}/{len(rows)} videos.")

def main():
    parser = argparse.ArgumentParser(description="Enrich Prom-King videos with TPDB tags.")
    parser.add_argument("--limit", type=int, default=1000, help="Number of videos to process")
    parser.add_argument("--site", type=str, default="sexyprn", help="Site to process (e.g. sexyprn)")
    parser.add_argument("--start-id", type=int, default=0, help="Start at video ID > this value")
    args = parser.parse_args()
    
    asyncio.run(enrich_backlog(limit=args.limit, site=args.site, start_id=args.start_id))

if __name__ == "__main__":
    main()
