import pytest
from pydantic import ValidationError
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.promking._models import (
    BatchAddTaxonomyRequest,
    BatchMetadataUpdateRequest,
    BatchTaxonomyMergeRequest,
    BatchTaxonomyGenderUpdateRequest,
    TermRef,
)
from app.routers.promking.taxonomies import batch_merge_terms, get_table_config
from app.routers.promking.videos import build_metadata_update_clause


def test_pornstars_taxonomy_maps_to_physical_pornstar_tables():
    config = get_table_config("pornstars")

    assert config.table == "pornstars"
    assert config.join_table == "video_pornstars"
    assert config.term_column == "pornstar_id"
    assert config.public_kind == "pornstars"


def test_term_ref_accepts_optional_gender():
    term = TermRef(id=1, name="Ada", slug="ada", gender="female")

    assert term.gender == "female"


def test_video_add_taxonomy_request_uses_pornstars_kind():
    request = BatchAddTaxonomyRequest(video_ids=[10, 11], kind="pornstars", term_ids=[3])

    assert request.kind == "pornstars"


def test_video_add_taxonomy_request_rejects_invalid_kind_for_writes():
    with pytest.raises(ValidationError):
        BatchAddTaxonomyRequest(video_ids=[10], kind="invalid", term_ids=[3])


def test_metadata_update_clause_only_allows_safe_video_fields():
    payload = BatchMetadataUpdateRequest(
        video_ids=[1, 2],
        updates={"title": "New title", "thumbnail_url": "https://example.com/t.jpg"},
    )

    set_sql, values = build_metadata_update_clause(payload.updates, first_param=2)

    assert "title = $2" in set_sql
    assert "thumbnail_url = $3" in set_sql
    assert values == ["New title", "https://example.com/t.jpg"]


def test_metadata_update_clause_rejects_unknown_fields():
    payload = BatchMetadataUpdateRequest(video_ids=[1], updates={"site": "fxv"})

    with pytest.raises(ValueError, match="Unsupported metadata field"):
        build_metadata_update_clause(payload.updates, first_param=2)


def test_pornstar_gender_request_rejects_invalid_gender():
    with pytest.raises(ValidationError):
        BatchTaxonomyGenderUpdateRequest(updates=[{"pornstar_id": 1, "gender": "robot"}])


@pytest.mark.anyio
async def test_batch_merge_keeps_merged_term_names_as_aliases():
    payload = BatchTaxonomyMergeRequest(primary_id=10, merge_from=[20, 30])
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {"id": 10}
    mock_conn.fetchval.return_value = 7
    mock_conn.fetch.return_value = [{"id": 20}, {"id": 30}]
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.taxonomies.get_pool", return_value=mock_pool):
        response = await batch_merge_terms(payload, "pornstars")

    assert response.merged_count == 2
    update_sql = mock_conn.fetch.call_args.args[0]
    assert "merged_into_id = $2" in update_sql


@pytest.mark.anyio
async def test_batch_merge_videos_preserves_audio_preview_and_sums_views():
    from app.routers.promking._models import BatchVideoMergeRequest
    from app.routers.promking.videos import batch_merge_videos

    payload = BatchVideoMergeRequest(primary_id=1, merge_from=[2], preserve_audio_preview=True)
    mock_conn = AsyncMock()
    mock_conn.fetchrow.return_value = {
        "id": 1,
        "title": "Primary Title",
        "slug": "primary-slug",
        "thumbnail_url": "https://img.com/1.jpg",
        "preview_url": "https://img.com/silent.mp4",
        "duration_seconds": 120,
        "views": 100,
        "qualities": None,
        "description": None,
        "source": "pornxp",
        "source_url": "https://pxp.cool/1",
    }
    mock_conn.fetch.return_value = [
        {
            "id": 2,
            "title": "Secondary Title",
            "slug": "secondary-slug",
            "thumbnail_url": "https://img.com/2.jpg",
            "preview_url": "/api/promking/media/cache/abc123audio.mp4",
            "duration_seconds": 130,
            "views": 50,
            "qualities": ["1080p"],
            "description": "Secondary description",
            "source": "1porn",
            "source_url": "https://1porn.tv/2",
        }
    ]
    mock_tx = MagicMock()
    mock_tx.__aenter__ = AsyncMock(return_value=None)
    mock_tx.__aexit__ = AsyncMock(return_value=None)
    mock_conn.transaction = MagicMock(return_value=mock_tx)
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

    with patch("app.routers.promking.videos.get_pool", return_value=mock_pool):
        res = await batch_merge_videos(payload)

    assert res.primary_id == 1
    assert res.merged_ids == [2]
    assert res.views == 150
    # Secondary preview is preserved because it has audio cache!
    assert res.preview_url == "/api/promking/media/cache/abc123audio.mp4"

