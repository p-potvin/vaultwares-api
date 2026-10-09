"""Generated previews served from the workstation, with the site's own preview as fallback."""
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch

from app.routers.promking._models import BatchRemotePreviewsRequest
from app.routers.promking.media import remote
from app.routers.promking.media.routes import router as media_router
from app.routers.promking.videos import batch_set_remote_previews

HASH = "a" * 64
OTHER = "b" * 64


@pytest.fixture
def shared_tube(tmp_path, monkeypatch):
    (tmp_path / "data" / "media").mkdir(parents=True)
    monkeypatch.setattr("app.routers.promking.media.routes._shared_tube_path", lambda: tmp_path)
    monkeypatch.setattr(remote, "_shared_tube_path", lambda: tmp_path)
    monkeypatch.setattr(remote, "_down_until", 0.0)
    monkeypatch.setattr(remote, "REMOTE_BASE", "http://lab.test")
    return tmp_path


def lab(monkeypatch, handler):
    monkeypatch.setattr(remote, "_client", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(media_router, prefix="/api/promking")
    return TestClient(app)


def test_local_file_is_served_without_asking_the_workstation(shared_tube, monkeypatch, client):
    (shared_tube / "data" / "media" / HASH).write_bytes(b"local-clip")
    lab(monkeypatch, lambda req: pytest.fail("workstation was asked"))

    res = client.get(f"/api/promking/media/cache/{HASH}.mp4")

    assert res.status_code == 200
    assert res.content == b"local-clip"


def test_missing_clip_streams_from_the_workstation_with_range(shared_tube, monkeypatch, client):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["range"] = req.headers.get("range")
        return httpx.Response(
            206,
            stream=httpx.ByteStream(b"0123"),
            headers={"content-type": "video/mp4", "content-range": "bytes 0-3/10", "accept-ranges": "bytes"},
        )

    lab(monkeypatch, handler)

    res = client.get(f"/api/promking/media/cache/{HASH}.mp4", headers={"Range": "bytes=0-3"})

    assert res.status_code == 206
    assert res.content == b"0123"
    assert res.headers["content-range"] == "bytes 0-3/10"
    assert "immutable" in res.headers["cache-control"]
    assert seen == {"url": f"http://lab.test/cache/{HASH}", "range": "bytes=0-3"}


def test_unreachable_workstation_redirects_to_the_original_preview(shared_tube, monkeypatch, client):
    remote.save_fallbacks([(HASH, 7, "https://cdn.example/preview.mp4")])

    def handler(req):
        raise httpx.ConnectError("down")

    lab(monkeypatch, handler)

    res = client.get(f"/api/promking/media/cache/{HASH}.mp4", follow_redirects=False)

    assert res.status_code == 302
    assert res.headers["location"] == "https://cdn.example/preview.mp4"
    assert res.headers["cache-control"] == "no-store"
    assert not remote.remote_available()  # cooldown: next requests skip the workstation


def test_clip_unknown_everywhere_is_404(shared_tube, monkeypatch, client):
    lab(monkeypatch, lambda req: httpx.Response(404))

    assert client.get(f"/api/promking/media/cache/{OTHER}.mp4").status_code == 404


def test_fallback_store_keeps_a_known_url_when_a_later_upsert_has_none(shared_tube):
    remote.save_fallbacks([(HASH, 7, "https://cdn.example/a.mp4")])
    remote.save_fallbacks([(HASH, 7, None)])

    assert remote.fallback_for_hash(HASH) == "https://cdn.example/a.mp4"
    assert remote.fallbacks_for_videos([7, 8]) == {7: "https://cdn.example/a.mp4"}


@pytest.mark.anyio
async def test_batch_remote_previews_remembers_the_external_preview(shared_tube):
    payload = BatchRemotePreviewsRequest(items=[
        {"video_id": 1, "media_hash": HASH},
        {"video_id": 2, "media_hash": OTHER, "fallback_url": "https://cdn.example/given.mp4"},
        {"video_id": 3, "media_hash": HASH},
    ])
    conn = AsyncMock()
    conn.transaction = MagicMock()
    conn.fetch.return_value = [
        {"id": 1, "preview_url": "https://cdn.example/old.mp4"},
        {"id": 2, "preview_url": "/api/promking/media/cache/x.mp4"},
    ]
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn

    with patch("app.routers.promking.videos.get_pool", AsyncMock(return_value=pool)):
        res = await batch_set_remote_previews(payload)

    assert res.count == 2
    assert [e.video_id for e in res.errors] == [3]
    ids, urls = conn.execute.await_args.args[1:]
    assert ids == [1, 2]
    assert urls == [f"/api/promking/media/cache/{HASH}.mp4", f"/api/promking/media/cache/{OTHER}.mp4"]
    assert remote.fallback_for_hash(HASH) == "https://cdn.example/old.mp4"
    assert remote.fallback_for_hash(OTHER) == "https://cdn.example/given.mp4"
