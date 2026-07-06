import httpx
import asyncio
import logging

logger = logging.getLogger(__name__)

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
    await asyncio.sleep(0.3)
    
    return {
        "categories": categories,
        "performers": performers,
        "studios": studios,
    }
