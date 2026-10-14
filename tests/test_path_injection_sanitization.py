"""
Regression tests for path injection vulnerability protections across api routers.
Proves correctness, persistence, and state roundtrip under real conditions.
"""
import asyncio
import hmac
import hashlib
import json
import time
import pytest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes_jobs import _job_path, _read_job, _write_job
from api.routes_media import api_open_downloaded, OpenPayload
from app.routers.promking.media.storage import sanitize_video_id, get_video_media_dir, get_media_file_path
from app.routers.promking.media.generator import generate_sprite_sheet
from app.routers.promking.media.routes import router as promking_media_router
from app.routers.monitor import router as monitor_router


def test_job_path_sanitization_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr("api.routes_jobs.JOBS_DIR", str(tmp_path))
    
    # 1. Valid job id pathing
    p = _job_path("job_12345abcdef")
    assert p is not None
    assert p.endswith("job_12345abcdef.json")
    assert Path(p).is_relative_to(tmp_path)
    
    # 2. State roundtrip persistence: write real job to disk and read back
    job_payload = {
        "id": "job_12345abcdef",
        "kind": "faceswap",
        "status": "queued",
        "created_at": time.time(),
        "payload": {"source": "img1.jpg", "target": "img2.jpg"}
    }
    _write_job(job_payload)
    assert Path(p).exists()
    
    # Read back and verify exact data persistence
    restored = _read_job("job_12345abcdef")
    assert restored is not None
    assert restored["id"] == "job_12345abcdef"
    assert restored["payload"]["source"] == "img1.jpg"
    
    # 3. Path traversal attempts are neutralized to base name or rejected
    traversal_path = _job_path("../../../etc/passwd")
    assert traversal_path is not None
    assert Path(traversal_path).name == "passwd.json"
    assert Path(traversal_path).parent == tmp_path
    assert Path(traversal_path).is_relative_to(tmp_path)
    
    # 4. Invalid or empty strings return None
    assert _job_path("") is None
    assert _job_path("///") is None
    assert _read_job("///") is None


def test_open_downloaded_path_traversal(tmp_path, monkeypatch):
    dest_dir = tmp_path / "downloads"
    dest_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("api.routes_media.ZIPPER_DEST_DIR", str(dest_dir))
    
    popen_calls = []
    monkeypatch.setattr("subprocess.Popen", lambda *args, **kwargs: popen_calls.append(args[0]))
    
    # Write a real downloaded file
    real_file = dest_dir / "sample.mp4"
    real_file.write_bytes(b"test-mp4-data")
    
    # 1. Valid filename succeeds
    res_valid = api_open_downloaded(OpenPayload(filename="sample.mp4"))
    assert res_valid["status"] == "success"
    assert "sample.mp4" in res_valid["message"]
    assert any("sample.mp4" in str(call) for call in popen_calls)
    
    # 2. Valid nested relative file in subfolder succeeds
    subfolder = dest_dir / "sub"
    subfolder.mkdir(parents=True, exist_ok=True)
    nested_file = subfolder / "nested.mp4"
    nested_file.write_bytes(b"nested-mp4-data")
    res_nested = api_open_downloaded(OpenPayload(path="sub/nested.mp4"))
    assert res_nested["status"] == "success"
    assert "nested.mp4" in res_nested["message"]
    assert any("nested.mp4" in str(call) for call in popen_calls)
    
    # 3. Path traversal attempt outside destination folder is rejected
    payload_traversal = OpenPayload(path="../../windows/system32/cmd.exe")
    res = api_open_downloaded(payload_traversal)
    assert res["status"] == "error"
    assert "Invalid target path" in res["message"]
    
    # 4. Folder open succeeds
    res_folder = api_open_downloaded(OpenPayload(folder=True))
    assert res_folder["status"] == "success"
    assert "downloaded folder" in res_folder["message"]


def test_promking_storage_video_id_sanitization(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMKING_MEDIA_DIR", str(tmp_path))
    
    # Valid numeric id
    assert sanitize_video_id(123) == 123
    assert sanitize_video_id("456") == 456
    
    # Invalid video ids raise ValueError
    with pytest.raises(ValueError):
        sanitize_video_id(-5)
    with pytest.raises(ValueError):
        sanitize_video_id("../../../etc")
    with pytest.raises(ValueError):
        sanitize_video_id("hack")
        
    # Valid get_video_media_dir creates real directory on disk within base
    v_dir = get_video_media_dir(999)
    assert v_dir.exists()
    assert v_dir.is_relative_to(tmp_path)
    
    # Path traversal on get_media_file_path returns None
    assert get_media_file_path("../../../999", "thumb.jpg") is None
    assert get_media_file_path(999, "../../../etc/passwd") is None
    assert get_media_file_path(-1, "thumb.jpg") is None


def test_promking_routes_http_traversal_rejection(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMKING_MEDIA_DIR", str(tmp_path))
    
    # Create real media file on disk
    v_dir = tmp_path / "777"
    v_dir.mkdir(parents=True, exist_ok=True)
    thumb_path = v_dir / "thumb.jpg"
    thumb_content = b"\xff\xd8\xff\xe0" + b"sample-jpeg-bytes" * 50
    thumb_path.write_bytes(thumb_content)
    
    app = FastAPI()
    app.include_router(promking_media_router, prefix="/api/promking")
    client = TestClient(app)
    
    # 1. Legitimate request fetches the real file
    res = client.get("/api/promking/media/onlyfans/777/thumb.jpg")
    assert res.status_code == 200
    assert res.content == thumb_content
    assert res.headers["content-type"] == "image/jpeg"
    
    # 2. Path traversal in filename returns 400 or 404
    res_bad = client.get("/api/promking/media/onlyfans/777/..%2f..%2fetc%2fpasswd")
    assert res_bad.status_code in (400, 404)
    
    # 3. Path traversal in video_id returns 404 or 422
    res_bad_id = client.get("/api/promking/media/onlyfans/..%2f777/thumb.jpg")
    assert res_bad_id.status_code in (404, 422)


def test_monitor_probe_rollup_persistence_and_traversal(tmp_path, monkeypatch):
    monkeypatch.setenv("VW_HEALTH_LEDGER_ROOT", str(tmp_path))
    secret = "test-secret-key-12345"
    monkeypatch.setenv("HEALTH_LEDGER_INGEST_SECRET", secret)
    
    app = FastAPI()
    app.include_router(monitor_router)
    client = TestClient(app)
    
    now = str(int(time.time()))
    payload_dict = {
        "probe_location_id": "greencloud-vps",
        "timestamp": now,
        "services": [{"name": "vaultwares-api", "status": "up"}]
    }
    body_bytes = json.dumps(payload_dict, separators=(",", ":")).encode("utf-8")
    
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        now.encode("ascii") + b"." + body_bytes,
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "x-health-ledger-timestamp": now,
        "x-health-ledger-signature": expected_sig,
        "content-type": "application/json"
    }
    
    # 1. Valid rollup ingest writes real file to disk
    res = client.post("/monitor/probe-rollups/greencloud-vps", content=body_bytes, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"status": "accepted", "location": "greencloud-vps"}
    
    # Verify file persisted on disk and contains expected services
    target_file = tmp_path / "data" / "rollups" / "locations" / "greencloud-vps.json"
    assert target_file.exists()
    saved = json.loads(target_file.read_text(encoding="utf-8"))
    assert saved["probe_location_id"] == "greencloud-vps"
    assert saved["services"][0]["name"] == "vaultwares-api"
    
    # 2. Unknown or traversal location_id is rejected with 404 and NO file written
    res_unknown = client.post("/monitor/probe-rollups/unknown-location", content=body_bytes, headers=headers)
    assert res_unknown.status_code == 404
    assert not (tmp_path / "data" / "rollups" / "locations" / "unknown-location.json").exists()
    
    res_traversal = client.post("/monitor/probe-rollups/..%2f..%2fdangerous", content=body_bytes, headers=headers)
    assert res_traversal.status_code in (404, 400)
    assert not (tmp_path / "dangerous.json").exists()


def test_promking_generate_sprite_sheet_metadata_on_invalid_id(tmp_path, monkeypatch):
    monkeypatch.setenv("PROMKING_MEDIA_DIR", str(tmp_path))
    # Negative video_id fails sanitize_video_id check, must return meta safely without UnboundLocalError
    sprite_url, sprite_vtt_url, meta = asyncio.run(
        generate_sprite_sheet(
            video_id=-999,
            video_url="http://example.com/test.mp4",
            duration=60.0,
            tile_count=12,
            tiles_per_row=4,
            tile_width=120,
            tile_height=80,
        )
    )
    assert sprite_url is None
    assert sprite_vtt_url is None
    assert isinstance(meta, dict)
    assert meta["tile_width"] == 120
    assert meta["tile_height"] == 80
    assert meta["tile_count"] == 12
    assert meta["tiles_per_row"] == 4
