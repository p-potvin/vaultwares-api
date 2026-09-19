"""
Unit tests for Prom-King OnlyFans Media Processing and Storage.
"""
import pytest
from pathlib import Path
from app.routers.promking.media.storage import (
    get_media_url,
    get_media_file_path,
    get_media_base_dir,
)
from app.routers.promking.media.generator import _format_vtt_time
from app.routers.promking.media.processor import _find_best_mp4_url, process_onlyfans_media
from app.routers.promking._models import VideoListItem, OnlyfansMediaOut


def test_vtt_time_formatting():
    assert _format_vtt_time(0.0) == "00:00:00.000"
    assert _format_vtt_time(65.5) == "00:01:05.500"
    assert _format_vtt_time(3661.123) == "01:01:01.123"


def test_find_best_mp4_url():
    # Test from qualities list
    qualities = [
        {"label": "720p", "url": "https://notfans.com/get_file/1/2/video.mp4", "type": "video/mp4"},
        {"label": "1080p", "url": "https://notfans.com/get_file/1/2/1080.mp4", "type": "video/mp4"},
    ]
    assert _find_best_mp4_url(qualities, None) == "https://notfans.com/get_file/1/2/video.mp4"

    # Test fallback to embed_url if qualities empty
    assert _find_best_mp4_url([], "https://notfans.com/get_file/1/2/direct.mp4") == "https://notfans.com/get_file/1/2/direct.mp4"

    # Non-mp4 embed returns None
    assert _find_best_mp4_url([], "https://notfans.com/embed/12345") is None


def test_media_urls_and_safe_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMKING_MEDIA_DIR", str(tmp_path))
    assert get_media_url(42, "thumb.jpg") == "/api/promking/media/onlyfans/42/thumb.jpg"
    assert get_media_url(42, "preview.mp4") == "/api/promking/media/onlyfans/42/preview.mp4"
    assert get_media_url(42, "sprite.jpg") == "/api/promking/media/onlyfans/42/sprite.jpg"

    # Valid filename path
    path = get_media_file_path(42, "thumb.jpg")
    assert path is not None
    assert path.name == "thumb.jpg"
    assert "42" in str(path)

    # Disallowed / path traversal filename
    assert get_media_file_path(42, "../../../etc/passwd") is None
    assert get_media_file_path(42, "hack.sh") is None


@pytest.mark.anyio
async def test_non_onlyfans_video_skips_media_processing():
    video_data = {
        "is_onlyfans": False,
        "source": "pornxp",
        "thumbnail_url": "https://pxp.cool/thumb.jpg",
    }
    result = await process_onlyfans_media(101, video_data, pool=None)
    assert result is None


def test_video_list_item_with_onlyfans_media():
    of_data = {
        "thumbnail_url": "/api/promking/media/onlyfans/123/thumb.jpg",
        "preview_video_url": "/api/promking/media/onlyfans/123/preview.mp4",
        "sprite_url": "/api/promking/media/onlyfans/123/sprite.jpg",
        "sprite_vtt_url": "/api/promking/media/onlyfans/123/sprite.vtt",
        "tile_width": 160,
        "tile_height": 90,
        "tile_count": 15,
        "tiles_per_row": 5,
        "interval_seconds": 12.5,
    }
    of_model = OnlyfansMediaOut(**of_data)
    assert of_model.tile_count == 15

    item = VideoListItem(
        id=123,
        title="Sample Video",
        slug="sample-video",
        created_at="2026-09-19T10:00:00Z",
        is_onlyfans=True,
        onlyfans_media=of_model,
        sprite_url=of_data["sprite_url"],
    )
    assert item.is_onlyfans is True
    assert item.onlyfans_media is not None
    assert item.onlyfans_media.sprite_url == "/api/promking/media/onlyfans/123/sprite.jpg"
    assert item.sprite_url == "/api/promking/media/onlyfans/123/sprite.jpg"


@pytest.mark.anyio
async def test_media_http_routes(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from app.routers.promking.media.routes import router as media_router

    monkeypatch.setenv("PROMKING_MEDIA_DIR", str(tmp_path))

    # Create dummy media files
    v_dir = tmp_path / "999"
    v_dir.mkdir(parents=True, exist_ok=True)
    thumb_file = v_dir / "thumb.jpg"
    thumb_file.write_bytes(b"\xff\xd8\xff\xe0" + b"dummy-jpeg-data" * 20)
    vtt_file = v_dir / "sprite.vtt"
    vtt_file.write_text("WEBVTT\n\n00:00:00.000 --> 00:00:10.000\nsprite.jpg#xywh=0,0,160,90", encoding="utf-8")
    preview_file = v_dir / "preview.mp4"
    preview_file.write_bytes(b"dummy-mp4-data" * 50)

    app = FastAPI()
    app.include_router(media_router, prefix="/api/promking")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch thumbnail
        res_thumb = await client.get("/api/promking/media/onlyfans/999/thumb.jpg")
        assert res_thumb.status_code == 200
        assert "image/jpeg" in res_thumb.headers["content-type"]
        assert "max-age=2592000" in res_thumb.headers["cache-control"]

        # 2. Fetch VTT
        res_vtt = await client.get("/api/promking/media/onlyfans/999/sprite.vtt")
        assert res_vtt.status_code == 200
        assert "text/vtt" in res_vtt.headers["content-type"]

        # 3. Fetch MP4 with Range
        res_mp4_range = await client.get(
            "/api/promking/media/onlyfans/999/preview.mp4",
            headers={"Range": "bytes=0-99"},
        )
        assert res_mp4_range.status_code == 206
        assert res_mp4_range.headers["content-range"].startswith("bytes 0-99/")
        assert len(res_mp4_range.content) == 100

        # 4. Nonexistent file returns 404
        res_404 = await client.get("/api/promking/media/onlyfans/999/missing.jpg")
        assert res_404.status_code == 404

        # 5. Invalid video_id or missing dir returns 404
        res_none = await client.get("/api/promking/media/onlyfans/111/thumb.jpg")
        assert res_none.status_code == 404
