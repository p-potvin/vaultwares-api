from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.routers.promking.tpdb import BatchItem, BatchRequest, resolve_tpdb_batch


@pytest.mark.anyio
async def test_resolve_tpdb_batch_returns_local_images_without_backfill_tasks():
    mock_conn = AsyncMock()
    mock_conn.fetch.side_effect = [
        [{"id": 1, "slug": "jane-star", "name": "Jane Star", "image_url": "https://img.example/jane.jpg"}],
        [],
    ]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    background_tasks = MagicMock()

    with patch("app.routers.promking.tpdb.get_pool", return_value=mock_pool):
        response = await resolve_tpdb_batch(
            BatchRequest(items=[BatchItem(type="performer", name="Jane Star")]),
            background_tasks,
        )

    assert response == {"results": {"performer:Jane Star": "https://img.example/jane.jpg"}}
    background_tasks.add_task.assert_not_called()


@pytest.mark.anyio
async def test_resolve_tpdb_batch_caps_missing_image_backfill_tasks():
    missing_rows = [
        {"id": idx + 1, "slug": f"star-{idx}", "name": f"Star {idx}", "image_url": None}
        for idx in range(500)
    ]
    mock_conn = AsyncMock()
    mock_conn.fetch.side_effect = [missing_rows, []]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn
    background_tasks = MagicMock()

    with patch("app.routers.promking.tpdb.get_pool", return_value=mock_pool):
        response = await resolve_tpdb_batch(
            BatchRequest(items=[BatchItem(type="performer", name=f"Star {idx}") for idx in range(500)]),
            background_tasks,
        )

    assert len(response["results"]) == 500
    assert background_tasks.add_task.call_count == 25
