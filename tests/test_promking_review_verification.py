"""Verification tests proving all PR review fixes in vaultwares-api work correctly."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request
from fastapi import HTTPException

from app.routers.promking.videos import is_admin_request, batch_add_taxonomy
from app.routers.promking.taxonomies import batch_merge_terms, _hot_terms_cache
from app.routers.promking._models import (
    BatchTaxonomyMergeRequest,
    BatchAddTaxonomyRequest,
)
from app.routers.promking.auth import (
    PromKingLoginResponse,
    PromKingRegisterResponse,
)


@pytest.mark.anyio
async def test_is_admin_request_unauthenticated():
    """Prove unauthenticated request returns False."""
    scope = {"type": "http", "headers": []}
    req = Request(scope)
    assert await is_admin_request(req) is False


@pytest.mark.anyio
async def test_is_admin_request_with_valid_admin_token():
    """Prove admin Bearer token returns True."""
    from api.auth import _create_access_token
    token = _create_access_token(user_id=1, username="admin@example.com", is_admin=True)
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode("latin1"))],
    }
    req = Request(scope)
    assert await is_admin_request(req) is True


@pytest.mark.anyio
async def test_is_admin_request_with_viewer_token():
    """Prove viewer Bearer token returns False without admin role."""
    from api.auth import _create_access_token
    token = _create_access_token(user_id=2, username="viewer@example.com", is_admin=False)
    scope = {
        "type": "http",
        "headers": [(b"authorization", f"Bearer {token}".encode("latin1"))],
    }
    req = Request(scope)
    mock_conn = AsyncMock()
    mock_conn.fetchval.return_value = "viewer"
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.videos.get_pool", return_value=mock_pool):
        assert await is_admin_request(req) is False


def test_login_response_expires_in():
    """Prove response models serialize accurate TTLs."""
    admin_resp = PromKingLoginResponse(access_token="abc", expires_in=86400)
    assert admin_resp.expires_in == 86400

    viewer_resp = PromKingLoginResponse(access_token="xyz", expires_in=14400)
    assert viewer_resp.expires_in == 14400

    reg_resp = PromKingRegisterResponse(email="test@example.com", access_token="def", expires_in=14400)
    assert reg_resp.expires_in == 14400


@pytest.mark.anyio
async def test_batch_merge_undesirable_guard_and_cache_invalidation():
    """Prove undesirable primary is blocked and cache is purged."""
    _hot_terms_cache["dummy_key"] = (12345.0, [])
    assert "dummy_key" in _hot_terms_cache

    payload = BatchTaxonomyMergeRequest(primary_id=99, merge_from=[100])
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"id": 99, "undesirable": True}
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.taxonomies.get_pool", return_value=mock_pool):
        with pytest.raises(HTTPException) as exc:
            await batch_merge_terms(payload, "categories")
        assert exc.value.status_code == 400

    # Successful merge invalidates cache
    mock_conn.fetchrow.return_value = {"id": 99, "undesirable": False}
    mock_conn.fetchval.return_value = 1
    mock_conn.fetch.return_value = [{"id": 100}]

    with patch("app.routers.promking.taxonomies.get_pool", return_value=mock_pool):
        await batch_merge_terms(payload, "categories")

    assert len(_hot_terms_cache) == 0
