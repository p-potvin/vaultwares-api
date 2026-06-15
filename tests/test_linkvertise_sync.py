import base64

import pytest

from app.services.zipper.linkvertise import (
    build_linkvertise_pair,
    infer_file_type,
    make_linkvertise_url,
)


def test_make_linkvertise_url_encodes_target(monkeypatch):
    monkeypatch.setenv("LINKVERTISE_USER_ID", "12345")
    monkeypatch.setenv("LINKVERTISE_RANDOM_ID", "678.9")

    target = "https://fboom.me/file/abc123"
    url = make_linkvertise_url(target)
    encoded = base64.b64encode(target.encode("utf-8")).decode("utf-8")

    assert url == f"https://link-to.net/12345/678.9/dynamic?r={encoded}"


@pytest.mark.parametrize(
    ("file_path", "title", "expected"),
    [
        ("C:/tmp/archive.zip", None, "zip"),
        ("C:/tmp/movie.mp4", None, "video"),
        (None, "movie.webm", "video"),
        ("C:/tmp/readme.nfo", None, "file"),
    ],
)
def test_infer_file_type(file_path, title, expected):
    assert infer_file_type(file_path, title) == expected


def test_build_linkvertise_pair_fileboom_mode_uses_fileboom_target(monkeypatch):
    monkeypatch.setenv("LINKVERTISE_USER_ID", "12345")
    monkeypatch.setenv("LINKVERTISE_RANDOM_ID", "dynamic")

    fileboom = "https://fboom.me/file/abc123"
    fxv, pkt = build_linkvertise_pair(
        fileboom_url=fileboom,
        slug="sample-video",
        target_mode="fileboom",
    )

    assert fxv == pkt
    assert fxv.endswith(base64.b64encode(fileboom.encode("utf-8")).decode("utf-8"))


def test_build_linkvertise_pair_prelander_mode_uses_branded_targets(monkeypatch):
    monkeypatch.setenv("LINKVERTISE_USER_ID", "12345")
    monkeypatch.setenv("LINKVERTISE_RANDOM_ID", "dynamic")

    fxv, pkt = build_linkvertise_pair(
        fileboom_url="https://fboom.me/file/abc123",
        slug="sample-video",
        file_path="sample-video.mp4",
        target_mode="prelander",
    )

    fxv_target = "https://links.fullxxx.video/video/sample-video"
    pkt_target = "https://links.prom-king.xyz/video/sample-video"
    assert fxv.endswith(base64.b64encode(fxv_target.encode("utf-8")).decode("utf-8"))
    assert pkt.endswith(base64.b64encode(pkt_target.encode("utf-8")).decode("utf-8"))
