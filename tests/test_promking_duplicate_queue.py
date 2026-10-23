import pytest
from app.routers.promking.videos import score_video_candidate
from app.routers.promking._models import (
    DuplicateCandidateItem,
    DuplicateClusterItem,
    DuplicateQueueResponse,
    BatchMergeQueueRequest,
    BatchMergeQueueResponse,
    MergeAllDuplicatesRequest,
    MergeAllDuplicatesResponse,
)


def test_score_video_candidate_prefers_audio_preview():
    v_normal = {
        "id": 100,
        "preview_url": "https://example.com/preview.mp4",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "duration_seconds": 1200,
        "views": 50,
    }
    v_audio = {
        "id": 101,
        "preview_url": "https://example.com/media/cache/abcd1234.mp4",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "duration_seconds": 1200,
        "views": 10,
    }

    score_normal = score_video_candidate(v_normal)
    score_audio = score_video_candidate(v_audio)

    assert score_audio > score_normal, "Audio-cached preview must score significantly higher"


def test_score_video_candidate_tie_break_earlier_id():
    v1 = {
        "id": 10,
        "preview_url": "https://example.com/preview.mp4",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "duration_seconds": 1200,
        "views": 50,
    }
    v2 = {
        "id": 20,
        "preview_url": "https://example.com/preview.mp4",
        "thumbnail_url": "https://example.com/thumb.jpg",
        "duration_seconds": 1200,
        "views": 50,
    }

    assert score_video_candidate(v1) > score_video_candidate(v2), "Earlier ID breaks ties"


def test_duplicate_models_instantiation():
    cand1 = DuplicateCandidateItem(
        id=1,
        title="Test Title",
        slug="test-title",
        views=100,
        score=15000.0,
    )
    cand2 = DuplicateCandidateItem(
        id=2,
        title="Test Title",
        slug="test-title-2",
        views=20,
        score=12000.0,
    )
    cluster = DuplicateClusterItem(
        title="Test Title",
        norm_title="test title",
        count=2,
        primary=cand1,
        secondaries=[cand2],
        total_views=120,
    )
    resp = DuplicateQueueResponse(
        total_clusters=1,
        total_duplicate_videos=2,
        redundant_count=1,
        clusters=[cluster],
    )
    assert resp.total_clusters == 1
    assert resp.redundant_count == 1
    assert len(resp.clusters) == 1
    assert resp.clusters[0].primary.id == 1
    assert resp.clusters[0].secondaries[0].id == 2
