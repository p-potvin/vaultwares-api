import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, BackgroundTasks
from app.routers.promking._models import FetchRunRequest
from app.routers.promking.fetcher import run_fetcher, _drive_subprocess


@pytest.mark.anyio
async def test_run_fetcher_validation_pornxp_fxv():
    # pornxp is allowed on fxv
    req = FetchRunRequest(site="fxv", source="pornxp", pages=3)
    bg = BackgroundTasks()
    
    mock_row = {"id": 42, "started_at": "2026-06-14T00:00:00Z"}
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = mock_row
    
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        handle = await run_fetcher(req, bg)
        assert handle.site == "fxv"
        assert handle.source == "pornxp"
        assert handle.pages == 3
        
        assert len(bg.tasks) == 1
        assert bg.tasks[0].func == _drive_subprocess


@pytest.mark.anyio
async def test_run_fetcher_validation_pornxp_allowed_everywhere():
    # pornxp is allowed on pkt (exclusivity removed)
    req = FetchRunRequest(site="pkt", source="pornxp", pages=3)
    bg = BackgroundTasks()
    
    mock_row = {"id": 43, "started_at": "2026-06-14T00:00:00Z"}
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = mock_row
    
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        handle = await run_fetcher(req, bg)
        assert handle.site == "pkt"
        assert handle.source == "pornxp"


@pytest.mark.anyio
async def test_run_fetcher_validation_oneporn_pkt():
    # 1porn is allowed on pkt
    req = FetchRunRequest(site="pkt", source="1porn", pages=3)
    bg = BackgroundTasks()
    
    mock_row = {"id": 43, "started_at": "2026-06-14T00:00:00Z"}
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = mock_row
    
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        handle = await run_fetcher(req, bg)
        assert handle.site == "pkt"
        assert handle.source == "1porn"
        
        assert len(bg.tasks) == 1
        assert bg.tasks[0].func == _drive_subprocess


@pytest.mark.anyio
async def test_run_fetcher_validation_oneporn_allowed_everywhere():
    # 1porn is allowed on fxv (exclusivity removed)
    req = FetchRunRequest(site="fxv", source="1porn", pages=3)
    bg = BackgroundTasks()
    
    mock_row = {"id": 44, "started_at": "2026-06-14T00:00:00Z"}
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = mock_row
    
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        handle = await run_fetcher(req, bg)
        assert handle.site == "fxv"
        assert handle.source == "1porn"


@pytest.mark.anyio
async def test_run_fetcher_validation_fullvideos_everywhere():
    # fullvideos is allowed anywhere, e.g. oneporn
    req = FetchRunRequest(site="oneporn", source="fullvideos", pages=3)
    bg = BackgroundTasks()
    
    mock_row = {"id": 44, "started_at": "2026-06-14T00:00:00Z"}
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = mock_row
    
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    
    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        handle = await run_fetcher(req, bg)
        assert handle.site == "oneporn"
        assert handle.source == "fullvideos"
        
        assert len(bg.tasks) == 1
        assert bg.tasks[0].func == _drive_subprocess
