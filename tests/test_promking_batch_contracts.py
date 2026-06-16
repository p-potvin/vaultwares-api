import pytest
from pydantic import ValidationError

from app.routers.promking._models import (
    BatchAddTaxonomyRequest,
    BatchMetadataUpdateRequest,
    BatchTaxonomyGenderUpdateRequest,
    TermRef,
)
from app.routers.promking.taxonomies import get_table_config
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


def test_video_add_taxonomy_request_rejects_actor_kind_for_writes():
    with pytest.raises(ValidationError):
        BatchAddTaxonomyRequest(video_ids=[10], kind="actors", term_ids=[3])


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
