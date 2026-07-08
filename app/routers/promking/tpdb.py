import httpx
import asyncio
import logging
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from .db import get_pool
from .taxonomies import slugify

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tpdb", tags=["promking:tpdb"])

TPDB_API_KEY = "LzLhKwMbmOnTIV6S576t5PUpELMot0yyRriatrgo517768e5"

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
            resp = await client.get(url, params=params, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
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
            
    # Optional delay to respect rate limit (can be handled by the caller, but adding a small sleep here is safe)
    # await asyncio.sleep(0.3)
    
    return {
        "categories": categories,
        "performers": performers,
        "studios": studios,
    }


class TpdbResolveResponse(BaseModel):
    imageUrl: str | None


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
            resp = await client.get(url, params=params, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
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
