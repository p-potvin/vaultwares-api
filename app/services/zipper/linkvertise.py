"""Helpers for deterministic Linkvertise URL generation."""
from __future__ import annotations

import base64
import os
from typing import Literal
from urllib.parse import urlparse

TargetMode = Literal["fileboom", "prelander"]

FXV_PRELANDER_BASE = "https://links.fullxxx.video"
PKT_PRELANDER_BASE = "https://links.prom-king.xyz"


def _require_http_url(value: str, field_name: str = "url") -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute http(s) URL")
    return value


def infer_file_type(file_path: str | None, title: str | None = None) -> str:
    name = (file_path or title or "").lower()
    if name.endswith(".zip"):
        return "zip"
    if name.endswith((".mp4", ".mkv", ".avi", ".mov", ".webm")):
        return "video"
    return "file"


def make_linkvertise_url(
    target_url: str,
    *,
    user_id: str | None = None,
    random_id: str | None = None,
) -> str:
    """Create the project-standard Linkvertise dynamic redirect URL."""
    target = _require_http_url(target_url, "target_url")
    account_id = user_id or os.environ.get("LINKVERTISE_USER_ID", "331075")
    link_id = random_id or os.environ.get("LINKVERTISE_RANDOM_ID", "dynamic")
    target_b64 = base64.b64encode(target.encode("utf-8")).decode("utf-8")
    return f"https://link-to.net/{account_id}/{link_id}/dynamic?r={target_b64}"


def build_linkvertise_pair(
    *,
    fileboom_url: str,
    slug: str,
    file_path: str | None = None,
    title: str | None = None,
    target_mode: TargetMode = "fileboom",
) -> tuple[str, str]:
    """Return FXV/PKT Linkvertise URLs for one link_sharing row.

    ``fileboom`` wraps the actual Fileboom URL directly. ``prelander`` wraps the
    existing branded link-sharing pages, which then resolve the Fileboom URL.
    """
    _require_http_url(fileboom_url, "fileboom_url")
    if target_mode == "fileboom":
        target_fxv = fileboom_url
        target_pkt = fileboom_url
    elif target_mode == "prelander":
        file_type = infer_file_type(file_path, title)
        target_fxv = f"{FXV_PRELANDER_BASE}/{file_type}/{slug}"
        target_pkt = f"{PKT_PRELANDER_BASE}/{file_type}/{slug}"
    else:
        raise ValueError(f"unsupported Linkvertise target mode: {target_mode}")

    return make_linkvertise_url(target_fxv), make_linkvertise_url(target_pkt)
