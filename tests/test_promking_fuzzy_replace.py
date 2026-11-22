import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.promking._models import (
    BatchTaxonomyReplacePair,
    BatchTaxonomyReplaceRequest,
)
from app.routers.promking.taxonomies import batch_replace_terms
from app.routers.promking.taxonomy.fuzzy_queue import compute_fuzzy_replace_queue


def _sample_rows():
    return [
        {"id": 10, "name": "Octokuro", "slug": "octokuro", "gender": "female", "image_url": None, "video_count": 50, "disabled": False, "undesirable": False},
        {"id": 11, "name": "Octokuro Model", "slug": "octokuro-model", "gender": "female", "image_url": None, "video_count": 1, "disabled": False, "undesirable": False},
        {"id": 20, "name": "Candy Alexa", "slug": "candy-alexa", "gender": "female", "image_url": None, "video_count": 35, "disabled": False, "undesirable": False},
        {"id": 21, "name": "Alexa Candy", "slug": "alexa-candy", "gender": "female", "image_url": None, "video_count": 1, "disabled": False, "undesirable": False},
        {"id": 30, "name": "Lauren Phillips", "slug": "lauren-phillips", "gender": "female", "image_url": None, "video_count": 200, "disabled": False, "undesirable": False},
        {"id": 31, "name": "Lauren Philips", "slug": "lauren-philips", "gender": "female", "image_url": None, "video_count": 1, "disabled": False, "undesirable": False},
        {"id": 40, "name": "Chloe Temple", "slug": "chloe-temple", "gender": "female", "image_url": None, "video_count": 230, "disabled": False, "undesirable": False},
        {"id": 41, "name": "Chloe Template", "slug": "chloe-template", "gender": "female", "image_url": None, "video_count": 1, "disabled": False, "undesirable": False},
        # Gender mismatch should be filtered when gender_compatible_only=True
        {"id": 50, "name": "Jordan Taylor", "slug": "jordan-taylor", "gender": "male", "image_url": None, "video_count": 20, "disabled": False, "undesirable": False},
        {"id": 51, "name": "Jordan Tayler", "slug": "jordan-tayler", "gender": "female", "image_url": None, "video_count": 1, "disabled": False, "undesirable": False},
        # 1v <-> 1v pair: only higher id -> lower id should appear
        {"id": 60, "name": "Amber Starling", "slug": "amber-starling", "gender": "female", "image_url": None, "video_count": 1, "disabled": False, "undesirable": False},
        {"id": 61, "name": "Amber Starlng", "slug": "amber-starlng", "gender": "female", "image_url": None, "video_count": 1, "disabled": False, "undesirable": False},
    ]


def test_compute_fuzzy_replace_queue_tiers_and_counts():
    res = compute_fuzzy_replace_queue(_sample_rows())
    assert res["counts_by_tier"] == {"2b": 1, "3": 1, "4a": 2, "4b": 1}
    assert res["total"] == 5

    by_src = {item["source"]["id"]: item for item in res["items"]}
    assert by_src[11]["tier"] == "2b"
    assert by_src[11]["target"]["id"] == 10
    assert by_src[21]["tier"] == "3"
    assert by_src[21]["target"]["id"] == 20
    assert by_src[31]["tier"] == "4a"
    assert by_src[31]["target"]["id"] == 30
    assert by_src[41]["tier"] == "4b"
    assert by_src[41]["target"]["id"] == 40
    assert by_src[61]["tier"] == "4a"
    assert by_src[61]["target"]["id"] == 60
    # Lower-id 1v item does not point back to higher-id 1v item
    assert 60 not in by_src
    # Gender mismatch excluded by default
    assert 51 not in by_src


def test_compute_fuzzy_replace_queue_filters_and_pagination():
    res_all_gender = compute_fuzzy_replace_queue(_sample_rows(), gender_compatible_only=False)
    assert any(item["source"]["id"] == 51 and not item["gender_compatible"] for item in res_all_gender["items"])

    res_multi_only = compute_fuzzy_replace_queue(_sample_rows(), multi_video_targets_only=True)
    assert all(item["target"]["video_count"] >= 2 for item in res_multi_only["items"])
    assert not any(item["source"]["id"] == 61 for item in res_multi_only["items"])

    res_tier_3 = compute_fuzzy_replace_queue(_sample_rows(), tier="3")
    assert res_tier_3["total"] == 1
    assert res_tier_3["counts_by_tier"]["2b"] == 1
    assert res_tier_3["items"][0]["source"]["id"] == 21

    res_search = compute_fuzzy_replace_queue(_sample_rows(), search="chloe")
    assert res_search["total"] == 1
    assert res_search["items"][0]["target"]["id"] == 40

    res_paged = compute_fuzzy_replace_queue(_sample_rows(), limit=2, offset=1)
    assert res_paged["total"] == 5
    assert len(res_paged["items"]) == 2


@pytest.mark.anyio
async def test_batch_replace_terms_hard_deletes_and_supports_split_targets():
    payload = BatchTaxonomyReplaceRequest(
        pairs=[
            BatchTaxonomyReplacePair(source_id=101, target_id=10),
            BatchTaxonomyReplacePair(source_id=102, target_ids=[20, 30]),
        ]
    )
    mock_conn = AsyncMock()
    mock_conn.fetchrow.side_effect = [
        {"id": 101},
        {"id": 102},
    ]
    mock_conn.fetch.side_effect = [
        [{"id": 10, "undesirable": False}],
        [{"id": 20, "undesirable": False}, {"id": 30, "undesirable": False}],
    ]
    mock_conn.fetchval.side_effect = [1, 1]
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.taxonomies.get_pool", return_value=mock_pool):
        res = await batch_replace_terms(payload, "pornstars")

    assert res.replaced_count == 2
    assert res.video_recount == 2
    assert res.errors == []

    execute_sqls = [str(call.args[0]) for call in mock_conn.execute.call_args_list]
    assert sum("INSERT INTO video_pornstars" in s and "unnest($2::int[])" in s for s in execute_sqls) == 2
    assert sum("DELETE FROM video_pornstars" in s for s in execute_sqls) == 2
    assert sum("UPDATE pornstars SET merged_into_id = $2" in s for s in execute_sqls) == 2
    assert sum("DELETE FROM pornstars WHERE id = $1" in s for s in execute_sqls) == 2
    assert not any("deleted_at = now()" in s for s in execute_sqls)


@pytest.mark.anyio
async def test_batch_replace_terms_rejects_undesirable_target_without_aborting_valid():
    payload = BatchTaxonomyReplaceRequest(
        pairs=[
            BatchTaxonomyReplacePair(source_id=201, target_id=999),
            BatchTaxonomyReplacePair(source_id=202, target_id=10),
        ]
    )
    mock_conn = AsyncMock()
    mock_conn.fetchrow.side_effect = [
        {"id": 201},
        {"id": 202},
    ]
    mock_conn.fetch.side_effect = [
        [{"id": 999, "undesirable": True}],
        [{"id": 10, "undesirable": False}],
    ]
    mock_conn.fetchval.side_effect = [1]
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.taxonomies.get_pool", return_value=mock_pool):
        res = await batch_replace_terms(payload, "pornstars")

    assert res.replaced_count == 1
    assert res.video_recount == 1
    assert len(res.errors) == 1
    assert res.errors[0].term_id == 201
    assert "undesirable" in res.errors[0].reason.lower()
