"""Stats dashboard backing data.

The v1 stats endpoint returned just video-per-source counts and recent
fetch_runs. The admin operator wanted richer breakdowns — view aggregates,
catalog-health signals, top-N tables, and a 7-day fetcher activity summary.
Everything the DB tracks is exposed here; anything we don't track (likes,
watch time, ad impressions) is intentionally absent so the client can flag
it as "not tracked yet" rather than showing a zero that looks wrong.

Schema note (2026-07-04 migration): `videos.site` was removed and replaced
with a `video_sites(video_id, site)` join table so a video can be surfaced
on multiple brands. Every "site" filter here now goes through
`JOIN video_sites vs ON vs.video_id = v.id AND vs.site = $x`. When the
caller passes `site=None` (global dashboard) we skip the join so counts
aren't multiplied per site.
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
    CatalogGrowth,
    TpdbEnrichment,
    DiscoveryHealthStats,
    SearchQuerySummary,
    DeadEndSearchSummary,
    ConversionSummary,
)

router = APIRouter(prefix="/stats", tags=["promking:stats"])


TOP_N_LIMIT = 10  # Enough for a scannable table without dwarfing the page.


def _scope_videos(site: Site | None) -> tuple[str, str, list]:
    """
    Return `(join_sql, where_sql, params)` that scopes a `videos v ...`
    query to `site`. When `site is None` returns a no-op no-join.

    Callers must alias `videos` as `v` and put the JOIN fragment right
    after `FROM videos v`. The WHERE fragment is combined with any other
    conditions the query already has.
    """
    if site is None:
        return "", "TRUE", []
    return (
        "JOIN video_sites vs ON vs.video_id = v.id",
        "vs.site = $1",
        [site],
    )


def _scope_runs(site: Site | None) -> tuple[str, list]:
    """`fetch_runs.site` is still a real column (the migration only touched
    videos), so this stays as a simple WHERE."""
    if site is None:
        return "TRUE", []
    return "site = $1", [site]


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
    join_videos, where_videos, videos_params = _scope_videos(site)
    where_runs, runs_params = _scope_runs(site)

    async with pool.acquire() as conn:
        # ── Totals per site (always cross-site so the admin can spot
        # data-import drift even when scoped). Joined through video_sites so
        # a single video that spans two brands is counted on each. ────────
        videos_total_rows = await conn.fetch(
            """
            SELECT vs.site::text AS site, COUNT(DISTINCT v.id) AS n
              FROM videos v
              JOIN video_sites vs ON vs.video_id = v.id
             GROUP BY vs.site
            """
        )

        # ── Per-source × site breakdown. Same join model — a video on two
        # brands with source=pornxp contributes to each brand's pornxp row.
        per_source_rows = await conn.fetch(
            f"""
            SELECT vs2.site::text AS site, v.source, COUNT(DISTINCT v.id) AS n
              FROM videos v
              JOIN video_sites vs2 ON vs2.video_id = v.id
              {join_videos}
             WHERE {where_videos}
             GROUP BY vs2.site, v.source
             ORDER BY {'v.source' if site else 'vs2.site, v.source'}
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

        # ── Views summary ────────────────────────────────────────────────
        views_row = await conn.fetchrow(
            f"""
            SELECT
              COALESCE(SUM(v.views), 0)::bigint AS total,
              COALESCE(AVG(v.views), 0)::float  AS avg_per_video,
              COALESCE(MAX(v.views), 0)::bigint AS max_single,
              COUNT(*) FILTER (WHERE v.views > 0)::bigint AS videos_with_views
            FROM videos v
            {join_videos}
            WHERE {where_videos}
            """,
            *videos_params,
        )

        # ── Catalog health ────────────────────────────────────────────────
        health_row = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*)::bigint AS total,
              COUNT(*) FILTER (WHERE v.disabled_at IS NOT NULL)::bigint AS disabled,
              COUNT(*) FILTER (WHERE v.thumbnail_url IS NULL OR v.thumbnail_url = '')::bigint AS missing_thumbnail,
              COUNT(*) FILTER (WHERE v.duration_seconds IS NULL OR v.duration_seconds = 0)::bigint AS missing_duration,
              COUNT(*) FILTER (WHERE v.description IS NULL OR v.description = '')::bigint AS missing_description
            FROM videos v
            {join_videos}
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
            SELECT v.id, v.slug, v.title, v.views, v.duration_seconds, v.thumbnail_url
              FROM videos v
              {join_videos}
             WHERE {where_videos}
               AND v.views > 0
             ORDER BY v.views DESC
             LIMIT {TOP_N_LIMIT}
            """,
            *videos_params,
        )

        # ── Top taxonomies (by video count + view sum) ────────────────────
        top_studios_rows = await _top_taxonomy(conn, "studios", "video_studios", "studio_id", site)
        top_pornstars_rows = await _top_taxonomy(conn, "pornstars", "video_pornstars", "pornstar_id", site)
        top_categories_rows = await _top_taxonomy(conn, "categories", "video_categories", "category_id", site)

        # Favourites — user + anon rows combined. Scoped via video_sites
        # when a site is set.
        favs_row = await conn.fetchrow(
            f"""
            SELECT COUNT(*)::bigint AS n
              FROM favourites f
              JOIN videos v ON v.id = f.video_id
              {join_videos}
             WHERE {where_videos}
            """,
            *videos_params,
        )

        # ── Catalog Growth Velocity ──────────────────────────────────────
        growth_row = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE v.created_at >= NOW() - INTERVAL '1 day')::bigint AS added_24h,
              COUNT(*) FILTER (WHERE v.created_at >= NOW() - INTERVAL '7 days')::bigint AS added_7d,
              COUNT(*) FILTER (WHERE v.created_at >= NOW() - INTERVAL '30 days')::bigint AS added_30d
            FROM videos v
            {join_videos}
            WHERE {where_videos}
            """,
            *videos_params,
        )

        # ── TPDB Enrichment ──────────────────────────────────────────────
        tpdb_row = await conn.fetchrow(
            f"""
            SELECT
              COUNT(DISTINCT ts.video_id)::bigint AS enriched_count,
              (COUNT(DISTINCT ts.video_id) * 100.0 / NULLIF(COUNT(DISTINCT v.id), 0))::float AS enrichment_pct
            FROM videos v
            {join_videos}
            LEFT JOIN tpdb_scenes ts ON ts.video_id = v.id
            WHERE {where_videos}
            """,
            *videos_params,
        )

        # ── Discovery Health ──────────────────────────────────────────────
        discovery_row = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM video_categories vc JOIN categories c ON c.id = vc.category_id WHERE vc.video_id = v.id AND c.disabled = false))::bigint AS no_categories,
              COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM video_pornstars vp JOIN pornstars p ON p.id = vp.pornstar_id WHERE vp.video_id = v.id AND p.disabled = false))::bigint AS no_pornstars,
              COUNT(*) FILTER (WHERE NOT EXISTS (SELECT 1 FROM video_studios vs JOIN studios s ON s.id = vs.studio_id WHERE vs.video_id = v.id AND s.disabled = false))::bigint AS no_studios
            FROM videos v
            {join_videos}
            WHERE {where_videos}
            """,
            *videos_params,
        )

        # ── Fetch Error Rate 7d ──────────────────────────────────────────
        error_rate_row = await conn.fetchrow(
            f"""
            SELECT
              (COUNT(*) FILTER (WHERE errors > 0) * 100.0 / NULLIF(COUNT(*), 0))::float AS run_error_rate
            FROM fetch_runs
            WHERE {where_runs}
              AND started_at >= NOW() - INTERVAL '7 days'
            """,
            *runs_params,
        )

        # ── Search Logs & Dead-ends ──────────────────────────────────────
        search_where = "TRUE"
        search_params = []
        if site:
            search_where = "site = $1"
            search_params = [site]

        top_searches_rows = await conn.fetch(
            f"""
            SELECT query, COUNT(*)::bigint AS n
            FROM search_logs
            WHERE {search_where}
            GROUP BY query
            ORDER BY n DESC, query ASC
            LIMIT 10
            """,
            *search_params,
        )

        top_dead_end_rows = await conn.fetch(
            f"""
            SELECT query, COUNT(*)::bigint AS n
            FROM search_logs
            WHERE {search_where} AND results_count = 0
            GROUP BY query
            ORDER BY n DESC, query ASC
            LIMIT 10
            """,
            *search_params,
        )

        # ── Conversions & Payouts ────────────────────────────────────────
        conversion_row = await conn.fetchrow(
            f"""
            SELECT
              COUNT(*)::bigint AS total_conversions,
              COALESCE(SUM(coalesce(nullif(payout, ''), '0')::float), 0.0)::float AS total_payout
            FROM postbacks
            WHERE {search_where}
            """,
            *search_params,
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
        catalog_growth=CatalogGrowth(
            added_24h=int(growth_row["added_24h"] or 0),
            added_7d=int(growth_row["added_7d"] or 0),
            added_30d=int(growth_row["added_30d"] or 0),
        ),
        tpdb_enrichment=TpdbEnrichment(
            enriched_count=int(tpdb_row["enriched_count"] or 0),
            enrichment_pct=float(tpdb_row["enrichment_pct"] or 0.0),
        ),
        discovery_health=DiscoveryHealthStats(
            no_categories=int(discovery_row["no_categories"] or 0),
            no_pornstars=int(discovery_row["no_pornstars"] or 0),
            no_studios=int(discovery_row["no_studios"] or 0),
        ),
        fetch_error_rate_7d=float(error_rate_row["run_error_rate"] or 0.0),
        top_searches=[SearchQuerySummary(query=r["query"], n=int(r["n"])) for r in top_searches_rows],
        top_dead_end_searches=[DeadEndSearchSummary(query=r["query"], n=int(r["n"])) for r in top_dead_end_rows],
        conversions=ConversionSummary(
            total_conversions=int(conversion_row["total_conversions"] or 0),
            total_payout=float(conversion_row["total_payout"] or 0.0),
        ),
    )


async def _top_taxonomy(conn, term_table: str, join_table: str, term_fk: str, site: Site | None):
    """Return the top-N taxonomy rows by video count with a matching view sum.
    Site-scoped via the video_sites join so per-site pages show only that
    brand's contribution."""
    join_videos, where_videos, params = _scope_videos(site)
    sql = f"""
        SELECT t.id, t.name, t.slug,
               COUNT(DISTINCT v.id)::bigint AS video_count,
               COALESCE(SUM(v.views), 0)::bigint AS view_sum
          FROM {term_table} t
          JOIN {join_table} j ON j.{term_fk} = t.id
          JOIN videos v ON v.id = j.video_id
          {join_videos}
         WHERE {where_videos} AND t.disabled = false
         GROUP BY t.id, t.name, t.slug
         ORDER BY view_sum DESC, video_count DESC
         LIMIT {TOP_N_LIMIT}
    """
    return await conn.fetch(sql, *params)
