import pytest
from app.routers.promking.stats import _scope_videos, _scope_runs, TOP_N_LIMIT
from app.routers.promking._models import StatsResponse


def test_scope_videos_none():
    join_sql, where_sql, params = _scope_videos(None)
    assert join_sql == ""
    assert where_sql == "TRUE"
    assert params == []


def test_scope_videos_site():
    join_sql, where_sql, params = _scope_videos("fxv")
    assert "video_sites vs ON vs.video_id = v.id" in join_sql
    assert where_sql == "vs.site = $1"
    assert params == ["fxv"]


def test_scope_runs_none():
    where_sql, params = _scope_runs(None)
    assert where_sql == "TRUE"
    assert params == []


def test_scope_runs_site():
    where_sql, params = _scope_runs("oneporn")
    assert where_sql == "site = $1"
    assert params == ["oneporn"]


def test_top_n_limit():
    assert TOP_N_LIMIT == 10
