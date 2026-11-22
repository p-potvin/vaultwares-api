import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.promking.stats import stats


@pytest.mark.anyio
async def test_stats_catalog_health_queries_global_active_catalog():
    captured_fetchrow_sqls: list[str] = []

    async def fake_fetch(sql, *args):
        return []

    async def fake_fetchrow(sql, *args):
        captured_fetchrow_sqls.append(str(sql))
        if "health_total" in str(sql):
            return {
                "views_total": 1000,
                "views_avg_per_video": 10.0,
                "views_max_single": 100,
                "videos_with_views": 50,
                "health_total": 110230,
                "health_active": 94705,
                "health_disabled": 15525,
                "health_missing_thumbnail": 0,
                "health_missing_duration": 3,
                "health_missing_description": 90819,
                "health_failed_preview": 70,
                "growth_added_24h": 1,
                "growth_added_7d": 5,
                "growth_added_30d": 20,
            }
        if "run_error_rate" in str(sql):
            return {"run_error_rate": 0.0}
        if "total_conversions" in str(sql):
            return {"total_conversions": 0, "total_payout": 0.0}
        if "enriched_count" in str(sql):
            return {"enriched_count": 7195}
        if "no_categories" in str(sql):
            return {"no_categories": 47352, "no_pornstars": 4067, "no_studios": 6506}
        if "COUNT(*)::bigint AS n" in str(sql):
            return {"n": 0}
        return {"runs": 0, "fetched": 0, "added": 0, "skipped": 0, "errors": 0}

    mock_conn = AsyncMock()
    mock_conn.fetch.side_effect = fake_fetch
    mock_conn.fetchrow.side_effect = fake_fetchrow
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.stats.get_pool", return_value=mock_pool):
        res = await stats(site="fxv")

    assert res.catalog_health is not None
    assert res.catalog_health.total == 110230
    assert res.catalog_health.disabled == 15525
    assert res.catalog_health.missing_description == 90819
    assert res.tpdb_enrichment is not None
    assert res.tpdb_enrichment.enriched_count == 7195
    assert res.tpdb_enrichment.enrichment_pct == pytest.approx(7195 * 100.0 / 94705)
    assert res.discovery_health is not None
    assert res.discovery_health.no_categories == 47352

    metrics_sql = next(s for s in captured_fetchrow_sqls if "health_total" in s)
    assert "JOIN video_sites" not in metrics_sql
    assert "v.disabled_at IS NULL" in metrics_sql
    assert "health_active" in metrics_sql

    tpdb_sql = next(s for s in captured_fetchrow_sqls if "enriched_count" in s)
    assert "FROM vault_raggae_scenes ts" in tpdb_sql
    assert "JOIN videos v ON v.id = ts.video_id" in tpdb_sql
    assert "v.disabled_at IS NULL" in tpdb_sql

    discovery_sql = next(s for s in captured_fetchrow_sqls if "no_categories" in s)
    assert "FROM videos WHERE disabled_at IS NULL" in discovery_sql
    for table in ("categories", "pornstars", "studios"):
        assert f"JOIN {table}" in discovery_sql
    assert discovery_sql.count("deleted_at IS NULL") == 3
    assert discovery_sql.count("disabled = false") == 3
    assert discovery_sql.count("undesirable = false") == 3
