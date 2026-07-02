"""Stats dashboard backing data.

The v1 stats endpoint returned just video-per-source counts and recent
fetch_runs. The admin operator wanted richer breakdowns — view aggregates,
catalog-health signals, top-N tables, and a 7-day fetcher activity summary.
Everything the DB tracks is exposed here; anything we don't track (likes,
watch time, ad impressions) is intentionally absent so the client can flag
it as "not tracked yet" rather than showing a zero that looks wrong.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from .db import get_pool
from ._models import (
    CatalogHealth,
    FetchActivity,
    FetchRunSummary,
    Site,
    StatsResponse,
    TopTermRef,
    TopVideoRef,
    ViewsSummary,
)

router = APIRouter(prefix="/stats", tags=["promking:stats"])


TOP_N_LIMIT = 10  # Enough for a scannable table without dwarfing the page.


def _scope_clause(site: Site | None, prefix: str = "") -> tuple[str, list]:
    """Return (fragment, params) that scopes rows to a given site, or a
    no-op fragment when site is None. `prefix` should be the table alias if
    the query joins."""
    if site is None:
        return "TRUE", []
    col = f"{prefix}site" if prefix else "site"
    return f"{col} = $1", [site]


@router.get("", response_model=StatsResponse)
async def stats(
    site: Site | None = Query(
        None,
        description=(
            "Scope every row to the given site. The admin always passes its "
            "current site; omit only for the global cross-site dashboard."
        ),
    ),
) -> StatsResponse:
    pool = await get_pool()
    where_videos, videos_params = _scope_clause(site)
    where_runs, runs_params = _scope_clause(site)

    async with pool.acquire() as conn:
        # ── Totals per site (pkt/oneporn/sexyprn always visible so the admin
        # can spot data-import drift even when scoped). Not filtered by site. ─
        videos_total_rows = await conn.fetch(
            "SELECT site::text AS site, COUNT(*) AS n FROM videos GROUP BY site"
        )

        per_source_rows = await conn.fetch(
            f"""
            SELECT site::text AS site, source, COUNT(*) AS n
            FROM videos
            WHERE {where_videos}
            GROUP BY site, source
            ORDER BY {'source' if site else 'site, source'}
            """,
            *videos_params,
        )

        runs_rows = await conn.fetch(
            f"""
            SELECT id, site::text AS site, source, started_at, finished_at,
                   fetched, added, skipped, errors
            FROM fetch_runs
            WHERE {where_runs}
            ORDER BY started_at DESC
            LIMIT 25
            """,
            *runs_params,
        )

        # ── Views summary (only meaningful when scoped or aggregated globally) ─
        views_row = await conn.fetchrow(
            f"""
            SELECT
              COALESCE(SUM(views), 0)::bigint AS total,
              COALESCE(AVG(views), 0)::float  AS avg_per_video,
              COALESCE(MAX(views), 0)::bigint AS max_single,
              COUNT(*) FILTER (WHERE views > 0)::bigint AS videos_with_views
            FROM videos
            WHERE {where_videos}
            """,
            *videos_params,
        )

        # ── Catalog health ────────────────────────────────────────────────
        health_row = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*)::bigint AS total,
              COUNT(*) FILTER (WHERE disabled_at IS NOT NULL)::bigint AS disabled,
              COUNT(*) FILTER (WHERE thumbnail_url IS NULL OR thumbnail_url = '')::bigint AS missing_thumbnail,
              COUNT(*) FILTER (WHERE duration_seconds IS NULL OR duration_seconds = 0)::bigint AS missing_duration,
              COUNT(*) FILTER (WHERE description IS NULL OR description = '')::bigint AS missing_description
            FROM videos
            WHERE {where_videos}
            """,
            *videos_params,
        )

        # ── 7-day fetch activity ──────────────────────────────────────────
        activity_row = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*)::bigint AS runs,
              COALESCE(SUM(fetched), 0)::bigint AS fetched,
              COALESCE(SUM(added), 0)::bigint   AS added,
              COALESCE(SUM(skipped), 0)::bigint AS skipped,
              COALESCE(SUM(errors), 0)::bigint  AS errors
            FROM fetch_runs
            WHERE {where_runs}
              AND started_at >= NOW() - INTERVAL '7 days'
            """,
            *runs_params,
        )

        # ── Top viewed videos ─────────────────────────────────────────────
        top_videos_rows = await conn.fetch(
            f"""
            SELECT id, slug, title, views, duration_seconds, thumbnail_url
            FROM videos
            WHERE {where_videos}
              AND views > 0
            ORDER BY views DESC
            LIMIT {TOP_N_LIMIT}
            """,
            *videos_params,
        )

        # ── Top taxonomies (by video count + view sum) ────────────────────
        # Joining video-view sums lets us rank talent by attention, not just
        # by "who has the most videos indexed". If a studio has 100 videos
        # with 5 views each vs. one with 1 video and 500 views, the second
        # tells the operator more about revenue.
        top_studios_rows = await _top_taxonomy(conn, "studios", "video_studios", "studio_id", site)
        top_pornstars_rows = await _top_taxonomy(conn, "pornstars", "video_pornstars", "pornstar_id", site)
        top_categories_rows = await _top_taxonomy(conn, "categories", "video_categories", "category_id", site)

        # Favourites — user + anon rows combined. Not site-scoped (fav rows
        # don't carry a site) — but the JOIN to videos means we still scope
        # by the videos' site column.
        favs_row = await conn.fetchrow(
            f"""
            SELECT COUNT(*)::bigint AS n
            FROM favourites f
            JOIN videos v ON v.id = f.video_id
            WHERE {where_videos.replace('site', 'v.site')}
            """,
            *videos_params,
        )

    views = ViewsSummary(
        total=int(views_row["total"] or 0),
        avg_per_video=float(views_row["avg_per_video"] or 0.0),
        max_single=int(views_row["max_single"] or 0),
        videos_with_views=int(views_row["videos_with_views"] or 0),
    )
    catalog_health = CatalogHealth(
        total=int(health_row["total"] or 0),
        disabled=int(health_row["disabled"] or 0),
        missing_thumbnail=int(health_row["missing_thumbnail"] or 0),
        missing_duration=int(health_row["missing_duration"] or 0),
        missing_description=int(health_row["missing_description"] or 0),
    )
    fetch_activity_7d = FetchActivity(
        window_days=7,
        runs=int(activity_row["runs"] or 0),
        fetched=int(activity_row["fetched"] or 0),
        added=int(activity_row["added"] or 0),
        skipped=int(activity_row["skipped"] or 0),
        errors=int(activity_row["errors"] or 0),
    )

    return StatsResponse(
        videos_total={r["site"]: int(r["n"]) for r in videos_total_rows},
        videos_per_source=[
            {"site": r["site"], "source": r["source"], "n": int(r["n"])}
            for r in per_source_rows
        ],
        fetch_runs_recent=[FetchRunSummary(**dict(r)) for r in runs_rows],
        views=views,
        catalog_health=catalog_health,
        fetch_activity_7d=fetch_activity_7d,
        top_videos=[
            TopVideoRef(
                id=r["id"], slug=r["slug"], title=r["title"], views=int(r["views"]),
                duration_seconds=r["duration_seconds"], thumbnail_url=r["thumbnail_url"],
            )
            for r in top_videos_rows
        ],
        top_studios=[TopTermRef(**dict(r)) for r in top_studios_rows],
        top_pornstars=[TopTermRef(**dict(r)) for r in top_pornstars_rows],
        top_categories=[TopTermRef(**dict(r)) for r in top_categories_rows],
        favourites_total=int(favs_row["n"] or 0),
    )


async def _top_taxonomy(conn, term_table: str, join_table: str, term_fk: str, site: Site | None):
    """Return the top-N taxonomy rows by video count with a matching view sum.
    Site-scoped via the videos join so per-site pages show only that site's
    contribution — a studio may look big globally but small on one brand."""
    where, params = _scope_clause(site, prefix="v.")
    sql = f"""
        SELECT t.id, t.name, t.slug,
               COUNT(DISTINCT v.id)::bigint AS video_count,
               COALESCE(SUM(v.views), 0)::bigint AS view_sum
        FROM {term_table} t
        JOIN {join_table} j ON j.{term_fk} = t.id
        JOIN videos v ON v.id = j.video_id
        WHERE {where}
        GROUP BY t.id, t.name, t.slug
        ORDER BY view_sum DESC, video_count DESC
        LIMIT {TOP_N_LIMIT}
    """
    return await conn.fetch(sql, *params)
