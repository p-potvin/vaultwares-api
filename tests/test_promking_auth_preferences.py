import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.promking._models import Site  # noqa: F401
from app.routers.promking.auth import (
    PromKingPreferencesUpdateRequest,
    me,
    update_preferences,
)


@pytest.mark.anyio
async def test_me_coerces_legacy_json_string_preferences():
    res_str = await me(
        current_user={
            "id": 8,
            "email": "clopeux",
            "role": "admin",
            "created_at": None,
            "preferences": '{"show_disabled": true}',
        }
    )
    assert res_str.preferences == {"show_disabled": True}

    res_dict = await me(
        current_user={
            "id": 8,
            "email": "clopeux",
            "role": "admin",
            "created_at": None,
            "preferences": {"show_disabled": False},
        }
    )
    assert res_dict.preferences == {"show_disabled": False}

    res_bad = await me(
        current_user={
            "id": 8,
            "email": "clopeux",
            "role": "admin",
            "created_at": None,
            "preferences": "not-json",
        }
    )
    assert res_bad.preferences == {}


@pytest.mark.anyio
async def test_update_preferences_passes_dict_not_json_string():
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        "id": 8,
        "email": "clopeux",
        "role": "admin",
        "created_at": None,
        "disabled_at": None,
        "preferences": {"show_disabled": True},
    }
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    payload = PromKingPreferencesUpdateRequest(preferences={"show_disabled": True})
    with patch("app.routers.promking.auth.get_pool", return_value=mock_pool):
        res = await update_preferences(
            payload,
            current_user={"id": 8, "email": "clopeux", "role": "admin"},
        )

    assert res.preferences == {"show_disabled": True}
    passed_pref = mock_conn.fetchrow.call_args.args[1]
    assert isinstance(passed_pref, dict)
    assert passed_pref == {"show_disabled": True}
