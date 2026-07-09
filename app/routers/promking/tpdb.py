import httpx
import asyncio
import json
import logging
from fastapi import APIRouter, BackgroundTasks, Query, HTTPException
from pydantic import BaseModel
from typing import Literal
from .db import get_pool
from .taxonomies import slugify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tpdb", tags=["promking:tpdb"])

TPDB_API_KEY = "LzLhKwMbmOnTIV6S576t5PUpELMot0yyRriatrgo517768e5"

_tpdb_lock = asyncio.Lock()
_current_delay = 0.1

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

async def fetch_tpdb_tags(title: str) -> dict | None:
    """
    Query the TPDB API to match a scene by title and extract its tags.
    Returns a dictionary of:
    {
      "categories": list[str],
      "performers": list[str],
      "studios": list[str],
    }
    or None if no match is found.
    """
    if not title:
        return None
        
    url = "https://api.theporndb.net/scenes"
    params = {"parse": title}
    headers = {
        "Authorization": f"Bearer {TPDB_API_KEY}",
        "Accept": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            data = await _make_tpdb_request(client, url, params, headers)
    except Exception as e:
        logger.warning(f"TPDB query failed for '{title}': {e}")
        return None
        
    if not data or not data.get("data"):
        return None
        
    scene = data["data"][0]
    
    categories = [tag["name"] for tag in scene.get("tags", [])]
    performers = [perf["name"] for perf in scene.get("performers", [])]
    
    studios = []
    site = scene.get("site")
    if site:
        studios.append(site["name"])
        network = site.get("network")
        if network and network.get("name") and network["name"] != site["name"]:
            studios.append(network["name"])

    # Persist the raw scene object to tpdb_scenes for future use
    try:
        pool = await get_pool()
        tpdb_id = str(scene.get("id") or "")
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO tpdb_scenes (title, tpdb_id, data)
                VALUES ($1, $2, $3)
                ON CONFLICT (tpdb_id) DO UPDATE SET data = EXCLUDED.data, title = EXCLUDED.title
                """,
                title, tpdb_id, json.dumps(scene)
            )
    except Exception as e:
        logger.warning(f"Failed to persist TPDB scene for '{title}': {e}")
    
    return {
        "categories": categories,
        "performers": performers,
        "studios": studios,
        "_scene": scene,
    }


class TpdbResolveResponse(BaseModel):
    imageUrl: str | None


class BatchItem(BaseModel):
    type: Literal["performer", "studio"]
    name: str


class BatchRequest(BaseModel):
    items: list[BatchItem]


async def _backfill_single(type_: str, name: str, slug: str, row_id: int) -> None:
    """Background task: fetch from TPDB and update the local DB for one missing image."""
    endpoint = "performers" if type_ == "performer" else "sites"
    url = f"https://api.theporndb.net/{endpoint}"
    params = {"q": name, "limit": 1}
    headers = {
        "Authorization": f"Bearer {TPDB_API_KEY}",
        "Accept": "application/json"
    }
    table = "pornstars" if type_ == "performer" else "studios"
    try:
        async with httpx.AsyncClient() as client:
            data = await _make_tpdb_request(client, url, params, headers)
        if not data or not data.get("data"):
            return
        items = data["data"]
        match = next(
            (i for i in items if i.get("image") or i.get("thumbnail") or i.get("face") or i.get("logo") or i.get("poster")),
            items[0]
        )
        if type_ == "performer":
            image_url = match.get("face") or match.get("thumbnail") or match.get("image")
            gender = match.get("gender", "").lower()
            if gender not in ("female", "male", "trans", "other"):
                gender = "unknown"
        else:
            image_url = match.get("logo") or match.get("poster") or match.get("image") or match.get("thumbnail")
            gender = None
        if not image_url:
            return
        pool = await get_pool()
        async with pool.acquire() as conn:
            if type_ == "performer" and gender and gender != "unknown":
                await conn.execute(
                    f"UPDATE {table} SET image_url = $1, gender = COALESCE(gender, $2::gender) WHERE id = $3",
                    image_url, gender, row_id
                )
            else:
                await conn.execute(
                    f"UPDATE {table} SET image_url = $1 WHERE id = $2",
                    image_url, row_id
                )
    except Exception as e:
        logger.warning(f"Background backfill failed for {type_} '{name}': {e}")


@router.get("/resolve", response_model=TpdbResolveResponse)
async def resolve_tpdb_image(
    q: str = Query(...),
    type: str = Query(...)  # 'performer' or 'studio'
) -> dict:
    """
    Check local DB first for an image for the given actor/studio.
    If none, proxy to TPDB API, fetch metadata, update local DB, and return image.
    """
    if type not in ("performer", "studio"):
        raise HTTPException(status_code=400, detail="type must be performer or studio")

    table = "pornstars" if type == "performer" else "studios"
    slug = slugify(q)
    
    # 1. Check local DB
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT id, image_url, name FROM {table} WHERE slug = $1 LIMIT 1",
            slug
        )
        # If we have a local record and it already has an image, just return it.
        if row and row["image_url"]:
            return {"imageUrl": row["image_url"]}

    # 2. Not in local DB or missing image. Hit TPDB.
    endpoint = "performers" if type == "performer" else "sites"
    url = f"https://api.theporndb.net/{endpoint}"
    params = {"q": q, "limit": 1}
    headers = {
        "Authorization": f"Bearer {TPDB_API_KEY}",
        "Accept": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            data = await _make_tpdb_request(client, url, params, headers)
    except Exception as e:
        logger.warning(f"TPDB resolve failed for {type} '{q}': {e}")
        return {"imageUrl": None}

    if not data or not data.get("data"):
        return {"imageUrl": None}

    # Find first item with an image
    items = data["data"]
    match = next((item for item in items if item.get("image") or item.get("thumbnail") or item.get("face") or item.get("logo") or item.get("poster")), items[0])

    if type == "performer":
        image_url = match.get("face") or match.get("thumbnail") or match.get("image")
        gender = match.get("gender", "").lower()
        if gender not in ("female", "male", "trans", "other"):
            gender = "unknown"
    else:
        image_url = match.get("logo") or match.get("poster") or match.get("image") or match.get("thumbnail")
        gender = None

    if not image_url:
        return {"imageUrl": None}

    # 3. Update local DB if row exists
    if row:
        async with pool.acquire() as conn:
            if type == "performer" and gender and gender != "unknown":
                await conn.execute(
                    f"UPDATE {table} SET image_url = $1, gender = COALESCE(gender, $2::gender) WHERE id = $3",
                    image_url, gender, row["id"]
                )
            else:
                await conn.execute(
                    f"UPDATE {table} SET image_url = $1 WHERE id = $2",
                    image_url, row["id"]
                )

    return {"imageUrl": image_url}


@router.post("/resolve-batch")
async def resolve_tpdb_batch(
    req: BatchRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """
    Batch resolver: look up image_url for a list of performers/studios from the
    local DB and return whatever we already have. For any row that is missing an
    image, enqueue a background TPDB fetch so the next request will hit the DB.

    Response shape: { "results": { "performer:Name": url | null, ... } }
    """
    if not req.items:
        return {"results": {}}

    pool = await get_pool()

    # Split by type so we can do two bulk lookups instead of N individual queries
    performer_names = [i.name for i in req.items if i.type == "performer"]
    studio_names    = [i.name for i in req.items if i.type == "studio"]
    performer_slugs = [slugify(n) for n in performer_names]
    studio_slugs    = [slugify(n) for n in studio_names]

    async with pool.acquire() as conn:
        ps_rows = await conn.fetch(
            "SELECT id, slug, name, image_url FROM pornstars WHERE slug = ANY($1) AND deleted_at IS NULL",
            performer_slugs
        ) if performer_slugs else []
        st_rows = await conn.fetch(
            "SELECT id, slug, name, image_url FROM studios WHERE slug = ANY($1) AND deleted_at IS NULL",
            studio_slugs
        ) if studio_slugs else []

    # Index by slug for O(1) lookup
    ps_by_slug = {r["slug"]: r for r in ps_rows}
    st_by_slug = {r["slug"]: r for r in st_rows}

    results: dict[str, str | None] = {}
    for item in req.items:
        key = f"{item.type}:{item.name}"
        slug = slugify(item.name)
        row = ps_by_slug.get(slug) if item.type == "performer" else st_by_slug.get(slug)

        if row and row["image_url"]:
            results[key] = row["image_url"]
        else:
            # Return None immediately; trigger background fetch if we have a DB row
            results[key] = None
            if row:
                background_tasks.add_task(
                    _backfill_single,
                    item.type, item.name, slug, row["id"]
                )

    return {"results": results}
