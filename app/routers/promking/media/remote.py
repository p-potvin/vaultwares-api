"""
Generated previews that live on the workstation, not on OVH.

The 7 x 1.5 s spliced previews for the whole catalog (~100k clips, 20-25 GB) don't fit on OVH,
so the workstation keeps them and serves them over the tailnet (tubevision lab, `GET /cache/<hash>`).
`/api/promking/media/cache/<hash>` streams from there when the file isn't in shared-tube's
`data/media`. When the workstation is down, the request is redirected to the site's original
preview, remembered here when `videos.preview_url` is switched to the generated clip.

Fallbacks live in a small SQLite file next to the media cache (`data/media-remote.sqlite`), not in
Postgres: the schema is owned by shared-tube's Drizzle models, and this is serving state, not catalog
data.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from pathlib import Path

import httpx

from ..fetcher import _shared_tube_path

# The workstation's lab, on the tailnet. Empty string disables remote serving.
REMOTE_BASE = os.environ.get("PROMKING_PREVIEW_REMOTE", "http://100.71.101.21:8790").rstrip("/")
# After a connection failure, skip the workstation for this long and go straight to the fallback.
COOLDOWN_SECONDS = 30.0

_client: httpx.AsyncClient | None = None
_down_until = 0.0
_db_lock = threading.Lock()


def client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=1.5),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=8),
        )
    return _client


def remote_available() -> bool:
    return bool(REMOTE_BASE) and time.monotonic() >= _down_until


def mark_down() -> None:
    global _down_until
    _down_until = time.monotonic() + COOLDOWN_SECONDS


def remote_url(media_hash: str) -> str:
    return f"{REMOTE_BASE}/cache/{media_hash}"


def _db_path() -> Path:
    return _shared_tube_path() / "data" / "media-remote.sqlite"


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS fallbacks ("
        " hash TEXT PRIMARY KEY, video_id INTEGER NOT NULL, fallback_url TEXT, updated_at REAL NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS fallbacks_video ON fallbacks (video_id)")
    return conn


def save_fallbacks(rows: list[tuple[str, int, str | None]]) -> None:
    """Upserts (hash, video_id, fallback_url). A NULL fallback never overwrites a known one."""
    now = time.time()
    with _db_lock:
        conn = _connect()
        try:
            with conn:
                conn.executemany(
                    "INSERT INTO fallbacks (hash, video_id, fallback_url, updated_at) VALUES (?, ?, ?, ?)"
                    " ON CONFLICT (hash) DO UPDATE SET video_id = excluded.video_id,"
                    " fallback_url = COALESCE(excluded.fallback_url, fallbacks.fallback_url),"
                    " updated_at = excluded.updated_at",
                    [(h, v, f, now) for h, v, f in rows],
                )
        finally:
            conn.close()


def fallback_for_hash(media_hash: str) -> str | None:
    if not _db_path().exists():
        return None
    with _db_lock:
        conn = _connect()
        try:
            row = conn.execute("SELECT fallback_url FROM fallbacks WHERE hash = ?", (media_hash,)).fetchone()
        finally:
            conn.close()
    return row[0] if row and row[0] else None


def fallbacks_for_videos(video_ids: list[int]) -> dict[int, str]:
    if not video_ids or not _db_path().exists():
        return {}
    with _db_lock:
        conn = _connect()
        try:
            q = ",".join("?" * len(video_ids))
            rows = conn.execute(
                f"SELECT video_id, fallback_url FROM fallbacks WHERE video_id IN ({q}) AND fallback_url IS NOT NULL"
                " ORDER BY updated_at",
                video_ids,
            ).fetchall()
        finally:
            conn.close()
    return {int(v): f for v, f in rows}
