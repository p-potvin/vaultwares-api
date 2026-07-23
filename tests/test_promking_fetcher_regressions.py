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
