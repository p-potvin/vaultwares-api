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

    assert "videos.site = $1" in where_sql
    assert "video_pornstars" in joins_sql
    assert "video_studios" in joins_sql
    assert "video_categories" in joins_sql
    assert "related_actors" in joins_sql
    assert "related_studios" in joins_sql
    assert "related_categories" in joins_sql
    assert "related_studios" in joins_sql
    assert "related_categories" in joins_sql
    assert "to_tsvector('english', videos.title)" in where_sql
    assert "actor_terms.slug = $3" in where_sql
    assert "studio_terms.slug = $4" in where_sql
    assert "category_terms.slug = $5" in where_sql
    assert "related_video.slug = $6" in where_sql
    assert "videos.slug <> $7" in where_sql
    assert params == [
        "pkt",
        "studio search",
        "jane-star",
        "sample-studio",
        "trending-hd",
        "current-video",
        "current-video",
    ]


def test_build_video_filters_disabled_and_source():
    # Test disabled=False, source="pornxp"
    where_sql, joins_sql, params = build_video_filters(
        site="fxv",
        disabled=False,
        source="pornxp"
    )
    assert "videos.site = $1" in where_sql
    assert "videos.disabled_at IS NULL" in where_sql
    assert "videos.source = $2" in where_sql
    assert params == ["fxv", "pornxp"]

    # Test disabled=True, source=None
    where_sql, joins_sql, params = build_video_filters(
        site="fxv",
        disabled=True
    )
    assert "videos.site = $1" in where_sql
    assert "videos.disabled_at IS NOT NULL" in where_sql
    assert "videos.source" not in where_sql
    assert params == ["fxv"]
