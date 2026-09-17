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
TPDB_BATCH_BACKFILL_LIMIT = 25

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

import re
from .taxonomy.dictionaries import KNOWN_STUDIOS, clean_title_for_search


def generate_candidate_scene_queries(
    title: str,
    studio_hint: str | None = None,
    performer_hints: list[str] | None = None,
) -> list[str]:
    """Generate candidate search strings to query TPDB /scenes endpoint.

    TPDB indexes scenes by their pure release title (e.g. "Shower Power",
    "Room Service"), whereas tube sites prepend studio and performer names
    (e.g. "Brazzers - Nicole Aniston - Shower Power 1080p").
    """
    candidates: list[str] = []
    cleaned = clean_title_for_search(title)
    if cleaned:
        candidates.append(cleaned)

    # Hyphen segment breakdown
    if " - " in title:
        parts = [p.strip() for p in title.split(" - ") if p.strip()]
        if len(parts) >= 2:
            last = clean_title_for_search(parts[-1])
            if last and last not in candidates:
                candidates.append(last)
        if len(parts) >= 3:
            mid_last = clean_title_for_search(f"{parts[-2]} {parts[-1]}")
            if mid_last and mid_last not in candidates:
                candidates.append(mid_last)

    # Strip studio hint from title
    stripped = cleaned
    if studio_hint:
        st_pat = re.compile(re.escape(studio_hint), re.IGNORECASE)
        stripped = st_pat.sub("", stripped).strip()
    for s in KNOWN_STUDIOS:
        if s in stripped.lower():
            st_pat = re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE)
            stripped = st_pat.sub("", stripped).strip()

    # Strip performers from title
    pure_title = stripped
    if performer_hints:
        for p in performer_hints:
            p_pat = re.compile(re.escape(p), re.IGNORECASE)
            pure_title = p_pat.sub("", pure_title).strip()

    pure_title = re.sub(r"\s+", " ", pure_title).strip()
    if pure_title and len(pure_title) >= 4 and pure_title not in candidates:
        candidates.append(pure_title)

    return candidates


async def fetch_tpdb_tags(
    title: str,
    performer_hints: list[str] | None = None,
    studio_hint: str | None = None,
) -> dict | None:
    """Query TPDB API using smart candidate queries to extract scene tags.

    Returns a dictionary of:
    {
      "categories": list[str],
      "performers": list[str],
      "studios": list[str],
      "_scene": dict,
    }
    or None if no match is found.
    """
    if not title:
        return None

    cleaned_title = clean_title_for_search(title)
    search_query = cleaned_title if cleaned_title else title

    # 1. Check local DB first
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT tpdb_id, data FROM tpdb_scenes WHERE title = $1 OR title = $2 LIMIT 1",
                title, search_query
            )
            if row:
                if row["tpdb_id"].startswith("notfound:"):
                    return None
                scene = json.loads(row["data"])
                categories = [tag["name"] for tag in scene.get("tags", [])]
                performers = [perf["name"] for perf in scene.get("performers", [])]
                studios = []
                site = scene.get("site")
                if site:
                    studios.append(site["name"])
                    network = site.get("network")
                    if network and network.get("name") and network["name"] != site["name"]:
                        studios.append(network["name"])
                return {
                    "categories": categories,
                    "performers": performers,
                    "studios": studios,
                    "_scene": scene,
                }
    except Exception as e:
        logger.warning(f"Failed to check local TPDB cache for '{title}': {e}")

    candidates = generate_candidate_scene_queries(title, studio_hint, performer_hints)
    url = "https://api.theporndb.net/scenes"
    headers = {
        "Authorization": f"Bearer {TPDB_API_KEY}",
        "Accept": "application/json"
    }

    best_match = None
    best_score = -1

    try:
        async with httpx.AsyncClient() as client:
            for q in candidates:
                data = await _make_tpdb_request(client, url, {"q": q, "limit": 10}, headers)
                items = (data or {}).get("data", [])
                if not items:
                    continue

                for item in items:
                    score = 0
                    site_name = (item.get("site") or {}).get("name", "").lower()
                    perf_names = [p["name"].lower() for p in item.get("performers", [])]
                    item_title = (item.get("title") or "").lower()

                    if studio_hint and studio_hint.lower() in site_name:
                        score += 20
                    for s in KNOWN_STUDIOS:
                        if s in site_name and s in title.lower():
                            score += 10

                    if performer_hints:
                        for ph in performer_hints:
                            if any(ph.lower() in pn for pn in perf_names):
                                score += 25
                    else:
                        for pn in perf_names:
                            if pn in title.lower():
                                score += 15

                    if item_title == q.lower():
                        score += 10
                    elif item_title in q.lower() or q.lower() in item_title:
                        score += 5

                    if score > best_score:
                        best_score = score
                        best_match = item

                # If we found a highly confident match, stop querying further candidates
                if best_score >= 30:
                    break
    except Exception as e:
        logger.warning(f"TPDB candidate query failed for '{title}': {e}")

    # If hints were provided, require a positive confidence score to avoid bogus mismatches
    if (studio_hint or performer_hints) and best_score < 15:
        return None

    if not best_match:
        return None

    scene = best_match
    categories = [tag["name"] for tag in scene.get("tags", [])]
    performers = [perf["name"] for perf in scene.get("performers", [])]

    studios = []
    site = scene.get("site")
    if site:
        studios.append(site["name"])
        network = site.get("network")
        if network and network.get("name") and network["name"] != site["name"]:
            studios.append(network["name"])

    # Persist the matched scene object to tpdb_scenes
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

async def verify_performer(name: str) -> dict | None:
    """Verify an unknown performer name against TPDB.

    Returns dict with canonical name, gender, and image_url if verified,
    or None if not found on TPDB.
    """
    clean_name = name.strip()
    if not clean_name:
        return None

    url = "https://api.theporndb.net/performers"
    params = {"q": clean_name, "limit": 1}
    headers = {
        "Authorization": f"Bearer {TPDB_API_KEY}",
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            data = await _make_tpdb_request(client, url, params, headers)
        items = data.get("data", [])
        if not items:
            return None
        match = items[0]
        canonical = match.get("name") or clean_name
        image = match.get("face") or match.get("thumbnail") or match.get("image")
        gender = (match.get("gender") or "unknown").lower()
        if gender not in ("female", "male", "trans", "other"):
            gender = "unknown"
        return {
            "name": canonical,
            "gender": gender,
            "image_url": image,
            "aliases": match.get("aliases", []),
        }
    except Exception as e:
        logger.warning(f"TPDB performer verification failed for '{name}': {e}")
        return None


async def fetch_tpdb_tags(title: str, performer_hints: list[str] | None = None) -> dict | None:
    """Query TPDB API using clean title search to extract scene tags.

    Returns a dictionary of:
    {
      "categories": list[str],
      "performers": list[str],
      "studios": list[str],
      "_scene": dict,
    }
    or None if no match is found.
    """
    if not title:
        return None

    cleaned_title = clean_title_for_search(title)
    search_query = cleaned_title if cleaned_title else title

    import hashlib
    title_hash = hashlib.md5(title.encode('utf-8')).hexdigest()
    not_found_id = f"notfound:{title_hash}"

    # 1. Check local DB first
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT tpdb_id, data FROM tpdb_scenes WHERE title = $1 OR title = $2 LIMIT 1",
                title, search_query
            )
            if row:
                if row["tpdb_id"].startswith("notfound:"):
                    return None
                scene = json.loads(row["data"])
                categories = [tag["name"] for tag in scene.get("tags", [])]
                performers = [perf["name"] for perf in scene.get("performers", [])]
                studios = []
                site = scene.get("site")
                if site:
                    studios.append(site["name"])
                    network = site.get("network")
                    if network and network.get("name") and network["name"] != site["name"]:
                        studios.append(network["name"])
                return {
                    "categories": categories,
                    "performers": performers,
                    "studios": studios,
                    "_scene": scene,
                }
    except Exception as e:
        logger.warning(f"Failed to check local TPDB cache for '{title}': {e}")

    url = "https://api.theporndb.net/scenes"
    headers = {
        "Authorization": f"Bearer {TPDB_API_KEY}",
        "Accept": "application/json"
    }

    data = None
    # Primary strategy: query with cleaned title
    try:
        async with httpx.AsyncClient() as client:
            data = await _make_tpdb_request(client, url, {"q": search_query}, headers)
            # Secondary fallback: if empty and we have performer hints, search performer names
            if (not data or not data.get("data")) and performer_hints:
                perf_q = " ".join(performer_hints[:2])
                if perf_q and perf_q != search_query:
                    data = await _make_tpdb_request(client, url, {"q": perf_q}, headers)
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

    # Persist the raw scene object to tpdb_scenes
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
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(f"UPDATE {table} SET image_url = '' WHERE id = $1", row_id)
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
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(f"UPDATE {table} SET image_url = '' WHERE id = $1", row_id)
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
        # If we have a local record and it already has an image (or was marked empty), return it.
        if row and row["image_url"] is not None:
            return {"imageUrl": row["image_url"] if row["image_url"] != "" else None}

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
        if row:
            async with pool.acquire() as conn:
                await conn.execute(f"UPDATE {table} SET image_url = '' WHERE id = $1", row["id"])
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
        if row:
            async with pool.acquire() as conn:
                await conn.execute(f"UPDATE {table} SET image_url = '' WHERE id = $1", row["id"])
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
    backfill_count = 0
    enqueued: set[tuple[str, str]] = set()
    for item in req.items:
        key = f"{item.type}:{item.name}"
        slug = slugify(item.name)
        row = ps_by_slug.get(slug) if item.type == "performer" else st_by_slug.get(slug)

        if row and row["image_url"] is not None:
            results[key] = row["image_url"] if row["image_url"] != "" else None
        else:
            # Return None immediately; trigger background fetch if we have a DB row (and it's not marked negative)
            results[key] = None
            backfill_key = (item.type, slug)
            if row and backfill_count < TPDB_BATCH_BACKFILL_LIMIT and backfill_key not in enqueued:
                background_tasks.add_task(
                    _backfill_single,
                    item.type, item.name, slug, row["id"]
                )
                enqueued.add(backfill_key)
                backfill_count += 1

    return {"results": results}
