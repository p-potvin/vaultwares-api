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

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .db import get_pool
from ._models import Site

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
     GROUP BY t.id, t.name, t.slug
     ORDER BY (t.name ILIKE $3) DESC, video_count DESC, t.name ASC
     LIMIT $4
"""

_GROUPS = {
    "pornstars": ("pornstars", "video_pornstars", "pornstar_id", "NULLIF(t.image_url, '')"),
    "studios": ("studios", "video_studios", "studio_id", "NULLIF(t.image_url, '')"),
    "categories": ("categories", "video_categories", "category_id", "NULL"),
}


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

    pool = await get_pool()
    async with pool.acquire() as conn:
        groups: dict[str, list[SuggestTerm]] = {}
        for key, (term_table, link_table, link_col, image_col) in _GROUPS.items():
            rows = await conn.fetch(
                _TAXONOMY_SQL.format(
                    term_table=term_table, link_table=link_table, link_col=link_col, image_col=image_col
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
