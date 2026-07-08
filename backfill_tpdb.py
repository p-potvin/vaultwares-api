import asyncio
import httpx
import json
import logging
from dotenv import load_dotenv

load_dotenv()

from app.routers.promking.db import get_pool
from app.routers.promking.tpdb import _make_tpdb_request, TPDB_API_KEY
from app.routers.promking.taxonomies import slugify

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")

async def process_batch(pool, table, rows, kind):
    async with httpx.AsyncClient() as client:
        for row in rows:
            id_ = row["id"]
            name = row["name"]
            slug = slugify(name)
            
            logger.info(f"Processing {kind}: {name} (id={id_})")
            
            endpoint = "performers" if kind == "performer" else "sites"
            url = f"https://api.theporndb.net/{endpoint}"
            params = {"q": name, "limit": 1}
            headers = {
                "Authorization": f"Bearer {TPDB_API_KEY}",
                "Accept": "application/json"
            }
            
            try:
                data = await _make_tpdb_request(client, url, params, headers)
            except Exception as e:
                logger.error(f"Failed to fetch {name}: {e}")
                continue
                
            if not data or not data.get("data"):
                logger.info(f"  -> No data found on TPDB")
                continue
                
            items = data["data"]
            match = next((item for item in items if item.get("image") or item.get("thumbnail") or item.get("face") or item.get("logo") or item.get("poster")), items[0])
            
            if kind == "performer":
                image_url = match.get("face") or match.get("thumbnail") or match.get("image")
                gender = match.get("gender", "").lower()
                if gender not in ("female", "male", "trans", "other"):
                    gender = "unknown"
            else:
                image_url = match.get("logo") or match.get("poster") or match.get("image") or match.get("thumbnail")
                gender = None
                
            if not image_url:
                logger.info(f"  -> No image found in TPDB data")
                continue
                
            async with pool.acquire() as conn:
                if kind == "performer" and gender and gender != "unknown":
                    await conn.execute(
                        f"UPDATE {table} SET image_url = $1, gender = COALESCE(gender, $2::gender) WHERE id = $3",
                        image_url, gender, id_
                    )
                    logger.info(f"  -> Updated image_url and gender ({gender})")
                else:
                    await conn.execute(
                        f"UPDATE {table} SET image_url = $1 WHERE id = $2",
                        image_url, id_
                    )
                    logger.info(f"  -> Updated image_url")


async def main():
    pool = await get_pool()
    
    # 1. Backfill pornstars
    logger.info("--- Backfilling pornstars ---")
    async with pool.acquire() as conn:
        pornstars = await conn.fetch("SELECT id, name FROM pornstars WHERE image_url IS NULL AND deleted_at IS NULL ORDER BY id DESC")
    logger.info(f"Found {len(pornstars)} pornstars to process.")
    await process_batch(pool, "pornstars", pornstars, "performer")
    
    # 2. Backfill studios
    logger.info("--- Backfilling studios ---")
    async with pool.acquire() as conn:
        studios = await conn.fetch("SELECT id, name FROM studios WHERE image_url IS NULL AND deleted_at IS NULL ORDER BY id DESC")
    logger.info(f"Found {len(studios)} studios to process.")
    await process_batch(pool, "studios", studios, "studio")
    
    logger.info("Done!")

if __name__ == "__main__":
    asyncio.run(main())
