from app.routers.promking.videos import build_video_filters


def test_build_video_filters_adds_taxonomy_and_related_clauses():
    where_sql, joins_sql, params = build_video_filters(
        site="pkt",
        q="studio search",
        actor="jane-star",
        studio="sample-studio",
        category="trending-hd",
        related_to="current-video",
        exclude_slug="current-video",
    )

    # `site` moved onto the video_sites join table in the 2026-07-04 migration;
    # this assertion still read `videos.site` and had been failing since.
    assert "video_sites.site = $1" in where_sql
    assert "video_pornstars" in joins_sql
    assert "video_studios" in joins_sql
    assert "video_categories" in joins_sql
    assert "related_actors" in joins_sql
    assert "related_studios" in joins_sql
    assert "related_categories" in joins_sql
    assert "to_tsvector('english', videos.title)" in where_sql
    # q now binds twice: the tsquery term and the ILIKE term, so the taxonomy
    # slug params shift up by one.
    assert "actor_terms.slug = $4" in where_sql
    assert "studio_terms.slug = $5" in where_sql
    assert "category_terms.slug = $6" in where_sql
    assert "related_video.slug = $7" in where_sql
    assert "videos.slug <> $8" in where_sql
    assert params == [
        "pkt",
        "studio search",
        "%studio search%",
        "jane-star",
        "sample-studio",
        "trending-hd",
        "current-video",
        "current-video",
    ]


def test_build_video_filters_q_matches_linked_taxonomy_names():
    """
    A bare title FTS made the most common tube queries return nothing —
    "brazzers" found 0 videos while the studio had 17 linked. q must also match
    the names of linked pornstars/studios/categories.
    """
    where_sql, _joins_sql, params = build_video_filters(site="fxv", q="brazzers")

    assert "to_tsvector('english', videos.title)" in where_sql
    assert "video_pornstars" in where_sql
    assert "video_studios" in where_sql
    assert "video_categories" in where_sql
    assert "ILIKE" in where_sql
    assert params == ["fxv", "brazzers", "%brazzers%"]


def test_build_video_filters_q_stays_non_correlated():
    """
    The taxonomy match must not be a correlated EXISTS. Correlated, Postgres
    re-runs a 17k-row ILIKE scan per candidate video: 24-33s against a copy of
    prod, versus ~150ms non-correlated. Guard the shape so it can't regress.
    """
    where_sql, _joins_sql, _params = build_video_filters(site="fxv", q="brazzers")

    assert "videos.id IN (SELECT" in where_sql
    assert "EXISTS" not in where_sql
    # The correlation predicate that would defeat the hashed subplan.
    assert "q_vp.video_id = videos.id" not in where_sql


def test_build_video_filters_q_does_not_join_taxonomy_tables():
    """
    Taxonomy matching lives in subqueries. A JOIN would emit one row per linked
    pornstar/studio/category and inflate both the grid and /count.
    """
    _where_sql, joins_sql, _params = build_video_filters(site="fxv", q="brazzers")

    # Only the site join should be present for a q-only filter.
    assert "video_sites" in joins_sql
    assert "JOIN video_pornstars" not in joins_sql
    assert "JOIN video_studios" not in joins_sql
    assert "JOIN video_categories" not in joins_sql


def test_build_video_filters_disabled_and_source():
    # Test disabled=False, source="pornxp"
    where_sql, joins_sql, params = build_video_filters(
        site="fxv",
        disabled=False,
        source="pornxp"
    )
    assert "video_sites.site = $1" in where_sql
    assert "videos.disabled_at IS NULL" in where_sql
    assert "videos.source = $2" in where_sql
    assert params == ["fxv", "pornxp"]

    # Test disabled=True, source=None
    where_sql, joins_sql, params = build_video_filters(
        site="fxv",
        disabled=True
    )
    assert "video_sites.site = $1" in where_sql
    assert "videos.disabled_at IS NOT NULL" in where_sql
    assert "videos.source" not in where_sql
    assert params == ["fxv"]
