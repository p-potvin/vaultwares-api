import asyncio
import httpx
import json
import logging
import os
import re
import asyncpg
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("backfill")

TPDB_API_KEY = "LzLhKwMbmOnTIV6S576t5PUpELMot0yyRriatrgo517768e5"
_tpdb_lock = asyncio.Lock()
_current_delay = 0.1

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text)
    return text.strip('-')

async def _register_json_codecs(conn: asyncpg.Connection) -> None:
    for typename in ("json", "jsonb"):
        await conn.set_type_codec(
            typename,
            encoder=json.dumps,
            decoder=json.loads,
            schema="pg_catalog",
        )

async def _make_tpdb_request(client: httpx.AsyncClient, url: str, params: dict, headers: dict) -> dict:
    global _current_delay
    async with _tpdb_lock:
        await asyncio.sleep(_current_delay)
        
        resp = await client.get(url, params=params, headers=headers, timeout=10.0)
        if resp.status_code == 429:
            logger.warning("TPDB rate limit hit, waiting 3s...")
            await asyncio.sleep(3.0)
            resp = await client.get(url, params=params, headers=headers, timeout=10.0)
            _current_delay = 0.1
        else:
            _current_delay = 0.1
            
        resp.raise_for_status()
        return resp.json()

async def process_batch(pool, table, rows, kind):
    async with httpx.AsyncClient() as client:
        for row in rows:
            id_ = row["id"]
            name = row["name"]
            
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
    dsn = os.environ.get("PROMKING_DATABASE_URL")
    if not dsn:
        dsn = "postgres://postgres:postgres@localhost:5432/promking"
        
    pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=1,
        max_size=10,
        init=_register_json_codecs,
    )
    
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
