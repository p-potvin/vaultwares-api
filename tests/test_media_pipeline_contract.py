import importlib
import os
from pathlib import Path
from unittest.mock import patch


def test_upscaler_lists_nomos_before_pillow_when_model_exists(monkeypatch, tmp_path):
    model = tmp_path / "4xNomos8k_atd.safetensors"
    model.write_bytes(b"stub")

    upscaler_module = importlib.import_module("app.services.upscaler")
    monkeypatch.setattr(upscaler_module, "MODELS_DIR", str(tmp_path))

    upscaler = upscaler_module.ImageUpscaler()

    assert upscaler.get_available_models()[:2] == ["4xNomos8k_atd", "pillow-lanczos"]
    assert upscaler.is_available()


def test_upscaler_keeps_pillow_available_without_model(monkeypatch, tmp_path):
    upscaler_module = importlib.import_module("app.services.upscaler")
    monkeypatch.setattr(upscaler_module, "MODELS_DIR", str(tmp_path))

    upscaler = upscaler_module.ImageUpscaler()

    assert upscaler.get_available_models() == ["pillow-lanczos"]
    assert upscaler.is_available()


def test_media_jobs_endpoint_marks_central_api_source():
    routes_media = importlib.import_module("api.routes_media")
    with routes_media.zipper_jobs_lock:
        routes_media.active_zipper_jobs.clear()
        routes_media.active_zipper_jobs["job-1"] = {"status": "running"}

    try:
        response = routes_media.api_get_jobs()
        assert response["source"] == "vaultwares-api"
        assert response["jobs"]["job-1"]["status"] == "running"
    finally:
        with routes_media.zipper_jobs_lock:
            routes_media.active_zipper_jobs.clear()


def test_rclone_handoff_tries_google_then_proton(monkeypatch, tmp_path):
    routes_media = importlib.import_module("api.routes_media")
    archive = tmp_path / "archive.zip"
    archive.write_bytes(b"zip")
    calls = []

    def fake_run(args, check, capture_output, text, timeout):
        calls.append(args)
        if "gdrive:python-zipper/" in args:
            raise routes_media.subprocess.CalledProcessError(1, args, stderr="quota")
        archive.unlink(missing_ok=True)
        return object()

    monkeypatch.setenv("VAULTWARES_RCLONE_REMOTES", "gdrive:python-zipper,proton:python-zipper")
    monkeypatch.setattr(routes_media.subprocess, "run", fake_run)

    result = routes_media.handoff_to_rclone(str(archive))

    assert result["status"] == "moved"
    assert calls[0][3] == "gdrive:python-zipper/"
    assert calls[1][3] == "proton:python-zipper/"
    assert not archive.exists()
