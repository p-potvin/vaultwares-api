"""
Search suggestions for the tube-site header typeahead.

One request per keystroke returns every group at once — pornstars, studios,
categories and previously-successful searches — ranked so the thing the user
means is first. The alternative (the client fanning out to
`/taxonomies/{kind}?q=`, which already supports ILIKE) would triple the request
volume per keystroke and couldn't rank across the groups.

Why entities and not just video titles: `/videos?q=` runs a full-text search over
`videos.title`, which is a bad match for how people search a tube. Suggesting the
pornstar/studio *entity* lets the client link straight to `/pornstar/<slug>` —
their whole catalogue — instead of a title search that finds a fraction of it.

Latency, measured against a copy of prod (69k videos, 17k pornstars) with a warm
cache: pornstars ~18ms, studios ~7ms, categories ~8ms, searches ~1.5ms; a
single-letter query — the worst case — ~54ms. The client still debounces and
requires 2 characters, so the single-letter case should rarely fire.
"""
from __future__ import annotations

import asyncio
import random
import time
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .db import get_pool
from ._models import Site
from .settings_routes import resolve_pornstar_gender

router = APIRouter(prefix="/search", tags=["promking:search"])

# Guard rails for a per-keystroke endpoint: cap the fan-out and ignore the
# single-character queries that are both slowest and least meaningful.
MIN_QUERY_LEN = 2
MAX_PER_GROUP = 8


class SuggestTerm(BaseModel):
    name: str
    slug: str
    video_count: int
    view_count: int
    thumbnail: Optional[str] = None


class SuggestSearch(BaseModel):
    query: str
    count: int


class SuggestResponse(BaseModel):
    query: str
    pornstars: list[SuggestTerm] = []
    studios: list[SuggestTerm] = []
    categories: list[SuggestTerm] = []
    searches: list[SuggestSearch] = []


# Only the table/column names vary between the three taxonomies, and they are
# module constants rather than caller input — never interpolate user data here.
#
# `t.deleted_at IS NULL` is required, not decorative: taxonomy deletion is a soft
# delete, and 206 pornstars / 45 studios are currently flagged. Without it the
# typeahead offers terms the operator has already deleted (verified: it suggested
# "Angel Youngs", deleted 2026-07-07), which /taxonomies correctly hides.
_TAXONOMY_SQL = """
    SELECT t.name, t.slug, COUNT(DISTINCT lt.video_id)::int AS video_count, COALESCE(SUM(v.views), 0)::int AS view_count, {image_col} AS thumbnail
      FROM {term_table} t
      JOIN {link_table} lt ON lt.{link_col} = t.id
      JOIN videos v        ON v.id = lt.video_id AND v.disabled_at IS NULL
      JOIN video_sites vs  ON vs.video_id = v.id AND vs.site = $1
     WHERE t.name ILIKE $2
       AND t.deleted_at IS NULL
       AND t.disabled = false
       AND t.undesirable = false
       {gender_filter}
       AND NOT EXISTS (SELECT 1 FROM video_pornstars vp JOIN pornstars p ON p.id = vp.pornstar_id WHERE vp.video_id = v.id AND p.disabled = true)
       AND NOT EXISTS (SELECT 1 FROM video_studios vs_s JOIN studios s ON s.id = vs_s.studio_id WHERE vs_s.video_id = v.id AND s.disabled = true)
       AND NOT EXISTS (SELECT 1 FROM video_categories vc JOIN categories c ON c.id = vc.category_id WHERE vc.video_id = v.id AND c.disabled = true)
     GROUP BY t.id, t.name, t.slug
     ORDER BY (t.name ILIKE $3) DESC, video_count DESC, t.name ASC
     LIMIT $4
"""

_GROUPS = {
    "pornstars": ("pornstars", "video_pornstars", "pornstar_id", "NULLIF(t.image_url, '')"),
    "studios": ("studios", "video_studios", "studio_id", "NULLIF(t.image_url, '')"),
    "categories": ("categories", "video_categories", "category_id", "NULL"),
}

_TRENDING_CACHE_TTL = 600.0
_trending_search_cache: dict[str, tuple[float, list[dict]]] = {}
_trending_locks: dict[str, asyncio.Lock] = {}
_trending_refreshing: set[str] = set()
_trending_cats_cache: tuple[float, list[dict], set[str]] | None = None
_trending_cats_lock = asyncio.Lock()


class TrendingSearchItem(BaseModel):
    query: str
    slug: Optional[str] = None
    recent_videos: int = 0
    total_videos: int = 0


class TrendingSearchesResponse(BaseModel):
    site: Site
    searches: list[str]
    items: list[TrendingSearchItem]


def _pornstar_gender_sql(gender: str) -> str:
    tok = (gender or "").strip().lower()
    if not tok or tok == "all":
        return ""
    if tok == "male":
        return "AND t.gender::text = 'male'"
    if tok == "female":
        return "AND t.gender::text = 'female'"
    if tok in ("female,null", "female,unknown"):
        return "AND (t.gender IS NULL OR t.gender::text IN ('female', 'unknown'))"
    return "AND (t.gender IS NULL OR t.gender::text <> 'male')"


async def _get_global_trending_categories() -> tuple[list[dict], set[str]]:
    global _trending_cats_cache
    now = time.monotonic()
    if _trending_cats_cache and now - _trending_cats_cache[0] < _TRENDING_CACHE_TTL:
        return _trending_cats_cache[1], _trending_cats_cache[2]

    async with _trending_cats_lock:
        now = time.monotonic()
        if _trending_cats_cache and now - _trending_cats_cache[0] < _TRENDING_CACHE_TTL:
            return _trending_cats_cache[1], _trending_cats_cache[2]

        pool = await get_pool()
        async with pool.acquire() as conn:
            cat_rows = await conn.fetch(
                """
                WITH recent_vids AS (
                    SELECT v.id, v.views, v.created_at
                    FROM videos v
                    WHERE v.disabled_at IS NULL
                      AND v.created_at >= NOW() - INTERVAL '7 days'
                )
                SELECT c.id,
                       c.name AS query,
                       c.slug AS slug,
                       COUNT(DISTINCT rv.id)::int AS recent_videos
                  FROM recent_vids rv
                  JOIN video_categories vc ON vc.video_id = rv.id
                  JOIN categories c ON c.id = vc.category_id
                 WHERE c.deleted_at IS NULL
                   AND c.disabled = false
                   AND c.undesirable = false
                   AND LENGTH(TRIM(c.name)) BETWEEN 3 AND 36
                 GROUP BY c.id, c.name, c.slug
                HAVING COUNT(DISTINCT rv.id) >= 3
                 ORDER BY recent_videos DESC,
                          COALESCE(SUM((rv.views + 1) * exp(-GREATEST(EXTRACT(EPOCH FROM (now() - rv.created_at)), 0) / 604800.0)), 0) DESC
                 LIMIT 60
                """
            )
            cat_ids = [int(r["id"]) for r in cat_rows]
            totals_map: dict[int, int] = {}
            if cat_ids:
                tot_rows = await conn.fetch(
                    """
                    SELECT vc.category_id, COUNT(*)::int AS cnt
                      FROM video_categories vc
                     WHERE vc.category_id = ANY($1::int[])
                     GROUP BY vc.category_id
                    """,
                    cat_ids,
                )
                totals_map = {int(r["category_id"]): int(r["cnt"] or 0) for r in tot_rows}

            male_rows = await conn.fetch(
                """
                SELECT LOWER(TRIM(name)) AS lname
                  FROM pornstars
                 WHERE gender::text = 'male'
                   AND deleted_at IS NULL
                """
            )
            male_names = {str(r["lname"]) for r in male_rows if r["lname"]}

        cats = [
            {
                "query": str(r["query"]).strip(),
                "slug": str(r["slug"]),
                "recent_videos": int(r["recent_videos"] or 0),
                "total_videos": totals_map.get(int(r["id"]), int(r["recent_videos"] or 0)),
            }
            for r in cat_rows
        ]
        _trending_cats_cache = (time.monotonic(), cats, male_names)
        return cats, male_names


async def _compute_trending_pool(site: str) -> list[dict]:
    cats, male_names = await _get_global_trending_categories()
    pool = await get_pool()
    async with pool.acquire() as conn:
        log_rows = await conn.fetch(
            """
            SELECT TRIM(sl.query) AS query,
                   COUNT(*)::int AS hits
              FROM search_logs sl
             WHERE sl.site = $1
               AND sl.results_count > 0
               AND sl.created_at >= NOW() - INTERVAL '30 days'
               AND LENGTH(TRIM(sl.query)) BETWEEN 3 AND 32
             GROUP BY TRIM(sl.query)
             ORDER BY hits DESC
             LIMIT 40
            """,
            site,
        )

    seen: set[str] = set()
    pool_items: list[dict] = []
    for item in cats:
        q_str = item["query"]
        key = q_str.lower()
        if key in seen:
            continue
        seen.add(key)
        pool_items.append(dict(item))
    for r in log_rows:
        q_str = str(r["query"]).strip()
        key = q_str.lower()
        if not q_str or key in seen or key in male_names:
            continue
        seen.add(key)
        pool_items.append({
            "query": q_str,
            "slug": None,
            "recent_videos": 0,
            "total_videos": int(r["hits"] or 0),
        })
        if len(pool_items) >= 85:
            break
    _trending_search_cache[site] = (time.monotonic(), pool_items)
    return pool_items


@router.get("/trending", response_model=TrendingSearchesResponse)
async def trending_searches(
    site: Site = Query(...),
    limit: int = Query(12, ge=1, le=50),
) -> TrendingSearchesResponse:
    """Return a per-request varied sample of trending live categories & successful queries."""
    now = time.monotonic()
    cached = _trending_search_cache.get(site)
    if cached:
        cached_ts, pool_items = cached
        if now - cached_ts >= _TRENDING_CACHE_TTL and site not in _trending_refreshing:
            _trending_refreshing.add(site)

            async def _bg_refresh(target_site: str) -> None:
                try:
                    await _compute_trending_pool(target_site)
                except Exception:
                    pass
                finally:
                    _trending_refreshing.discard(target_site)

            asyncio.create_task(_bg_refresh(site))
    else:
        lock = _trending_locks.setdefault(site, asyncio.Lock())
        async with lock:
            cached = _trending_search_cache.get(site)
            if cached:
                pool_items = cached[1]
            else:
                pool_items = await _compute_trending_pool(site)

    # Rotate every request while giving fresher/higher-volume items higher odds:
    # keep the top 2 freshest/hottest anchored near the front among top candidates,
    # and shuffle a weighted sample from the live pool so each SSR request varies.
    if len(pool_items) <= limit:
        picked = list(pool_items)
        random.shuffle(picked)
    else:
        head_pool = list(pool_items[: min(18, len(pool_items))])
        tail_pool = list(pool_items[min(18, len(pool_items)) :])
        head_k = min(len(head_pool), max(1, (limit * 2) // 3))
        picked_head = random.sample(head_pool, head_k)
        need_tail = limit - len(picked_head)
        remaining = [x for x in tail_pool] + [x for x in head_pool if x not in picked_head]
        picked_tail = random.sample(remaining, min(need_tail, len(remaining)))
        picked = picked_head + picked_tail
        random.shuffle(picked)

    return TrendingSearchesResponse(
        site=site,
        searches=[item["query"] for item in picked],
        items=[TrendingSearchItem(**item) for item in picked],
    )


@router.get("/suggest", response_model=SuggestResponse)
async def suggest(
    site: Site = Query(...),
    q: str = Query(..., description="Partial term the user has typed."),
    limit: int = Query(6, ge=1, le=MAX_PER_GROUP),
) -> SuggestResponse:
    """Typeahead suggestions for `q`, grouped and ranked."""
    term = q.strip()
    if len(term) < MIN_QUERY_LEN:
        return SuggestResponse(query=term)

    contains = f"%{term}%"
    # Prefix hits rank above mid-word ones: typing "chl" should surface
    # "Chloe Temple" before someone with "chl" buried in their name.
    prefix = f"{term}%"
    default_gender = await resolve_pornstar_gender(site)

    pool = await get_pool()
    async with pool.acquire() as conn:
        groups: dict[str, list[SuggestTerm]] = {}
        for key, (term_table, link_table, link_col, image_col) in _GROUPS.items():
            gender_filter = _pornstar_gender_sql(default_gender) if key == "pornstars" else ""
            rows = await conn.fetch(
                _TAXONOMY_SQL.format(
                    term_table=term_table,
                    link_table=link_table,
                    link_col=link_col,
                    image_col=image_col,
                    gender_filter=gender_filter,
                ),
                site,
                contains,
                prefix,
                limit,
            )
            groups[key] = [SuggestTerm(**dict(r)) for r in rows]

        # Past searches that actually returned something. Dead-end queries are
        # tracked in /stats precisely because they're worth *not* suggesting.
        search_rows = await conn.fetch(
            """
            SELECT query, COUNT(*)::int AS count
              FROM search_logs
             WHERE site = $1 AND query ILIKE $2 AND results_count > 0
             GROUP BY query
             ORDER BY count DESC, query ASC
             LIMIT $3
            """,
            site,
            contains,
            limit,
        )

    return SuggestResponse(
        query=term,
        pornstars=groups["pornstars"],
        studios=groups["studios"],
        categories=groups["categories"],
        searches=[SuggestSearch(**dict(r)) for r in search_rows],
    )
