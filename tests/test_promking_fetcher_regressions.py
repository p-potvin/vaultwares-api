import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.promking.fetcher import (
    RunState,
    _finalize_run,
    _merge_validated_term_names,
)


@pytest.mark.anyio
async def test_finalize_run_uses_run_state_query_fields_without_req_attr():
    state = RunState(
        run_id="abc",
        site="fxv",
        source="pornxp",
        pages=3,
        term_name="Old Name",
        db_run_id=12,
    )
    state.summary = {"fetched": 4, "added": 2, "skipped": 2, "errors": 0}

    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        await _finalize_run(state)

    args = mock_conn.execute.call_args.args
    assert args[1:6] == (12, 4, 2, 2, 0)
    assert args[6]["query"] == "Old Name"


def test_merge_validated_term_names_keeps_exact_local_names_before_tpdb_names():
    merged = _merge_validated_term_names(
        source_names=["Old Star", "Unverified Star"],
        local_matches={"old star": {"name": "Canonical Star", "disabled": False}},
        tpdb_names=["Canonical Star", "Verified Star"],
    )

    assert merged == ["Canonical Star", "Verified Star"]


def test_merge_validated_term_names_drops_unmatched_source_names_without_tpdb_validation():
    merged = _merge_validated_term_names(
        source_names=["Unverified Star"],
        local_matches={},
        tpdb_names=[],
    )

    assert merged == []


def test_expand_link_aliases_fullvideos_and_pornxp():
    from app.routers.promking.fetcher import _expand_link_aliases

    links = ["https://www.fullvideos.to/videos/123/title/"]
    expanded = _expand_link_aliases(links)
    assert "https://www.fullvideos.to/videos/123/title/" in expanded
    assert "https://www.fullvideos.xxx/videos/123/title/" in expanded

    pxp_links = ["https://pxp.cool/videos/456"]
    pxp_expanded = _expand_link_aliases(pxp_links)
    assert "https://pxp.cool/videos/456" in pxp_expanded
    assert "https://pornxp.bz/videos/456" in pxp_expanded
    assert "https://pornxp.fo/videos/456" in pxp_expanded


def test_filter_duplicate_candidates_dedupes_batch_and_site_slugs():
    from app.routers.promking.fetcher import filter_duplicate_candidates

    candidates = [
        {"sourceUrl": "https://www.fullvideos.to/videos/1/", "title": "First Scene"},
        {"sourceUrl": "https://www.fullvideos.to/videos/1/", "title": "First Scene Dupe URL"},
        {"sourceUrl": "https://www.fullvideos.to/videos/2/", "title": "First Scene"},  # Dupe slug
        {"sourceUrl": "https://www.fullvideos.to/videos/3/", "title": "Already in DB URL"},
        {"sourceUrl": "https://www.fullvideos.to/videos/4/", "title": "Already in DB Slug"},
        {"sourceUrl": "https://www.fullvideos.to/videos/5/", "title": "Unique Valid Scene"},
    ]

    existing_urls = {"https://www.fullvideos.to/videos/3/"}
    existing_site_slugs = {"already-in-db-slug"}

    filtered = filter_duplicate_candidates(candidates, existing_urls, existing_site_slugs)

    assert len(filtered) == 2
    assert filtered[0]["sourceUrl"] == "https://www.fullvideos.to/videos/1/"
    assert filtered[1]["sourceUrl"] == "https://www.fullvideos.to/videos/5/"


@pytest.mark.anyio
async def test_check_existing_links_matches_alias_domains():
    from app.routers.promking.fetcher import check_existing_links

    mock_conn = AsyncMock()
    # Database has legacy fullvideos.xxx row
    mock_conn.fetch.return_value = [{"source_url": "https://www.fullvideos.xxx/videos/123/"}]

    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        # Scraper provides canonical fullvideos.to URL
        found = await check_existing_links("fxv", ["https://www.fullvideos.to/videos/123/"])
        assert "https://www.fullvideos.to/videos/123/" in found
