"""
Prom-King OnlyFans Media Storage Operations.
Handles directory resolution, file paths, and safe URL mapping for OnlyFans media assets.
"""
from __future__ import annotations

import os
from pathlib import Path

def get_media_base_dir() -> Path:
    """
    Returns the root directory for OnlyFans media files.
    Respects PROMKING_MEDIA_DIR environment variable, otherwise falls back to
    the shared-tube data directory or a local data path.
    """
    env_dir = os.environ.get("PROMKING_MEDIA_DIR")
    if env_dir and env_dir.strip():
        base = Path(env_dir.strip()).resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base

    shared_tube_env = os.environ.get("PROMKING_SHARED_TUBE_PATH")
    if shared_tube_env and shared_tube_env.strip():
        base = (Path(shared_tube_env.strip()) / "data" / "onlyfans_media").resolve()
        base.mkdir(parents=True, exist_ok=True)
        return base

    # Try OVH repo layout: /srv/repos/Prom-King/shared-tube/data/onlyfans_media
    default_ovh = Path("/srv/repos/Prom-King/shared-tube/data/onlyfans_media")
    if default_ovh.parent.exists():
        default_ovh.mkdir(parents=True, exist_ok=True)
        return default_ovh

    # Local dev sibling repo layout: .../Prom-King/shared-tube/data/onlyfans_media
    repo_root = Path(__file__).resolve().parents[4]
    sibling_pk = (repo_root.parent / "Prom-King" / "shared-tube" / "data" / "onlyfans_media").resolve()
    if sibling_pk.parent.exists():
        sibling_pk.mkdir(parents=True, exist_ok=True)
        return sibling_pk

    # Fallback under repo data directory
    local_base = (repo_root / "data" / "onlyfans_media").resolve()
    local_base.mkdir(parents=True, exist_ok=True)
    return local_base


def sanitize_video_id(video_id: int | str) -> int:
    """Sanitizes and validates video_id, ensuring it is a positive integer."""
    input_str = str(video_id).strip()
    raw_str = os.path.basename(input_str)
    if not input_str.isdigit() or raw_str != input_str:
        raise ValueError(f"Invalid video_id: {video_id}")
    val = int(raw_str)
    if val <= 0:
        raise ValueError(f"Invalid video_id: {video_id}")
    return val


def get_video_media_dir(video_id: int | str) -> Path:
    """Returns the dedicated directory for a specific video's media files."""
    valid_id = sanitize_video_id(video_id)
    safe_name = os.path.basename(str(valid_id))
    base = get_media_base_dir().resolve()
    v_dir = (base / safe_name).resolve()
    if not v_dir.is_relative_to(base) or v_dir == base:
        raise ValueError(f"Invalid video directory path for video_id: {video_id}")
    v_dir.mkdir(parents=True, exist_ok=True)
    return v_dir


def get_media_url(video_id: int | str, filename: str) -> str:
    """Returns the canonical public API URL for a media asset."""
    valid_id = sanitize_video_id(video_id)
    safe_filename = os.path.basename(filename)
    return f"/api/promking/media/onlyfans/{valid_id}/{safe_filename}"


def get_media_file_path(video_id: int | str, filename: str) -> Path | None:
    """
    Returns the absolute path to a media file if safe and contained within the video dir.
    Guards against path traversal attacks.
    """
    allowed_filenames = {
        "thumb.jpg",
        "thumb.webp",
        "thumb.png",
        "preview.mp4",
        "preview.webp",
        "sprite.jpg",
        "sprite.webp",
        "sprite.vtt",
    }
    safe_filename = os.path.basename(filename)
    if safe_filename not in allowed_filenames or safe_filename != filename:
        return None

    try:
        base = get_media_base_dir().resolve()
        v_dir = get_video_media_dir(video_id)
        target = (v_dir / safe_filename).resolve()
        if not target.is_relative_to(base) or not target.is_relative_to(v_dir):
            return None
        return target
    except ValueError:
        return None
