import json
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


@pytest.mark.anyio
async def test_get_and_set_cursors():
    from app.routers.promking.fetcher import get_all_cursors, set_cursor, CursorUpdateRequest

    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"value": json.dumps({"pornxp": 42, "1porn": 10})}
    mock_conn.transaction = MagicMock()
    mock_conn.transaction.return_value.__aenter__.return_value = None
    mock_conn.transaction.return_value.__aexit__.return_value = False
    
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_pool.acquire.return_value.__aexit__.return_value = False

    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        cursors = await get_all_cursors(site="fxv")
        assert cursors == {"pornxp": 42, "1porn": 10}

        update_req = CursorUpdateRequest(site="fxv", source="pornxp", page=43)
        res = await set_cursor(update_req)
        assert res["ok"] is True
        assert res["page"] == 43


@pytest.mark.anyio
async def test_finalize_run_broadcasts_done_event_with_summary():
    import asyncio
    from app.routers.promking.fetcher import RunState, _finalize_run

    state = RunState(
        run_id="test-run-123",
        site="sexyprn",
        source="pornxp",
        pages=1,
        summary={"fetched": 10, "added": 0, "skipped": 10, "errors": 0},
    )
    q: asyncio.Queue[str] = asyncio.Queue()
    state.queues.append(q)

    # Run _finalize_run without db_run_id so it skips DB update and broadcasts
    await _finalize_run(state)

    # Queue should receive done event first, then closed
    msg1 = await q.get()
    data1 = json.loads(msg1)
    assert data1["event"] == "done"
    assert data1["summary"] == {"fetched": 10, "added": 0, "skipped": 10, "errors": 0}

    msg2 = await q.get()
    data2 = json.loads(msg2)
    assert data2["event"] == "closed"


@pytest.mark.anyio
async def test_finalize_run_with_db_run_id_updates_db_and_broadcasts():
    import asyncio
    from app.routers.promking.fetcher import RunState, _finalize_run

    state = RunState(
        run_id="test-run-456",
        db_run_id=99,
        site="sexyprn",
        source="pornxp",
        pages=1,
        summary={"fetched": 20, "added": 5, "skipped": 15, "errors": 0},
    )
    q: asyncio.Queue[str] = asyncio.Queue()
    state.queues.append(q)

    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.fetcher.get_pool", return_value=mock_pool):
        await _finalize_run(state)

    mock_conn.execute.assert_called_once()
    args = mock_conn.execute.call_args[0]
    assert "UPDATE fetch_runs" in args[0]
    assert args[1] == 99  # id
    assert args[2] == 20  # fetched
    assert args[3] == 5   # added
    assert args[4] == 15  # skipped

    msg1 = await q.get()
    assert json.loads(msg1)["event"] == "done"
    assert json.loads(msg1)["summary"] == {"fetched": 20, "added": 5, "skipped": 15, "errors": 0}

    msg2 = await q.get()
    assert json.loads(msg2)["event"] == "closed"


