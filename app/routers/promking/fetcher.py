"""
Fetcher bridge — POST /run spawns the shared-tube TS CLI as a subprocess and
emits NDJSON to stdout. GET /stream/{run_id} relays those NDJSON lines as
Server-Sent Events to the admin console. Persistence (insert into `videos`)
happens here in FastAPI once the CLI emits the final `videos` event.

The CLI lives at: shared-tube/shared/src/fetcher/cli.ts
The wire format is documented at:
  Prom-King/shared-tube/docs/router-integration.md

Env vars:
  PROMKING_SHARED_TUBE_PATH   absolute path to the shared-tube checkout
                              (default: ../../Prom-King/shared-tube relative to pipelines)
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from .db import get_pool
from ._models import FetchRunHandle, FetchRunRequest

router = APIRouter(prefix="/fetcher", tags=["promking:fetcher"])


# ─── Run registry (in-memory) ──────────────────────────────────────────────

@dataclass
class RunState:
    run_id: str
    site: str
    source: str
    pages: int
    db_run_id: Optional[int] = None
    process: Optional[asyncio.subprocess.Process] = None
    # Subscribers receive each NDJSON line as it arrives.
    queues: list[asyncio.Queue[str]] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)
    finished: bool = False
    error: Optional[str] = None


_runs: dict[str, RunState] = {}
_runs_lock = asyncio.Lock()


# ─── POST /fetcher/run ─────────────────────────────────────────────────────

@router.post("/run", response_model=FetchRunHandle)
async def run_fetcher(req: FetchRunRequest, bg: BackgroundTasks) -> FetchRunHandle:
    run_id = uuid.uuid4().hex
    state = RunState(run_id=run_id, site=req.site, source=req.source, pages=req.pages)
    async with _runs_lock:
        _runs[run_id] = state

    # Open the fetch_runs row first so the run is queryable while it streams.
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO fetch_runs (site, source, started_at)
            VALUES ($1, $2, NOW())
            RETURNING id, started_at
            """,
            req.site,
            req.source,
        )
    state.db_run_id = int(row["id"])

    # Spawn the subprocess in the background.
    bg.add_task(_drive_subprocess, state)
    return FetchRunHandle(
        run_id=run_id,
        site=req.site,
        source=req.source,
        pages=req.pages,
        started_at=row["started_at"],
    )


# ─── GET /fetcher/stream/{run_id} ──────────────────────────────────────────

@router.get("/stream/{run_id}")
async def stream_run(run_id: str) -> StreamingResponse:
    async with _runs_lock:
        state = _runs.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="unknown run")
    queue: asyncio.Queue[str] = asyncio.Queue()
    state.queues.append(queue)

    async def gen() -> AsyncIterator[bytes]:
        try:
            # Heartbeat so the SSE conn doesn't get nginx-reaped.
            last_beat = time.time()
            while True:
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=15.0)
                except asyncio.TimeoutError:
                    if state.finished and queue.empty():
                        break
                    if time.time() - last_beat > 14:
                        yield b": heartbeat\n\n"
                        last_beat = time.time()
                    continue
                last_beat = time.time()
                # Each NDJSON line becomes an SSE `data:` chunk.
                yield f"data: {line}\n\n".encode("utf-8")
                if state.finished and queue.empty():
                    break
        finally:
            try:
                state.queues.remove(queue)
            except ValueError:
                pass

    return StreamingResponse(gen(), media_type="text/event-stream")


# ─── GET /fetcher/runs ─────────────────────────────────────────────────────

@router.get("/runs")
async def recent_runs(limit: int = 25) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, site::text AS site, source, started_at, finished_at,
                   fetched, added, skipped, errors
            FROM fetch_runs
            ORDER BY started_at DESC
            LIMIT $1
            """,
            min(max(limit, 1), 200),
        )
    return [dict(r) for r in rows]


# ─── subprocess driver ────────────────────────────────────────────────────

def _shared_tube_path() -> Path:
    env = os.environ.get("PROMKING_SHARED_TUBE_PATH")
    if env:
        return Path(env)
    # Default: sibling repo layout — vaultwares-pipelines/.. / Prom-King/shared-tube
    return (
        Path(__file__).resolve().parents[3] / ".." / "Prom-King" / "shared-tube"
    ).resolve()


async def _drive_subprocess(state: RunState) -> None:
    cli = _shared_tube_path() / "shared" / "src" / "fetcher" / "cli.ts"
    if not cli.exists():
        state.error = f"fetcher CLI not found at {cli}"
        await _broadcast(state, json.dumps({"event": "error", "message": state.error}))
        await _finalize_run(state)
        return

    # Use the workspace's tsx via pnpm (deterministic Node 22 + ESM + TS).
    cmd = [
        "pnpm",
        "--filter",
        "@promking/shared-tube",
        "fetcher:run",
        "--",
        f"--site={state.site}",
        f"--source={state.source}",
        f"--pages={state.pages}",
    ]
    cwd = _shared_tube_path()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        state.error = f"failed to spawn pnpm: {e}"
        await _broadcast(state, json.dumps({"event": "error", "message": state.error}))
        await _finalize_run(state)
        return

    state.process = proc

    assert proc.stdout is not None
    videos_payload: list[dict] = []
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip("\n")
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # Non-JSON output → wrap as a log line so the console still sees it.
            payload = {"event": "log", "line": text}
        await _broadcast(state, json.dumps(payload))
        event = payload.get("event")
        if event == "done":
            summary = payload.get("summary") or {}
            state.summary = {
                "fetched": int(summary.get("fetched", 0)),
                "added": int(summary.get("added", 0)),
                "skipped": int(summary.get("skipped", 0)),
                "errors": int(summary.get("errors", 0)),
            }
        elif event == "videos":
            videos_payload = list(payload.get("videos") or [])

    return_code = await proc.wait()
    if return_code != 0 and not state.error:
        state.error = f"fetcher exited with code {return_code}"

    # Persist whatever the CLI returned. The CLI itself never writes.
    added = await _persist_videos(state.site, videos_payload)
    state.summary["added"] = added
    await _finalize_run(state)


async def _broadcast(state: RunState, line: str) -> None:
    for q in list(state.queues):
        try:
            q.put_nowait(line)
        except asyncio.QueueFull:
            pass


async def _finalize_run(state: RunState) -> None:
    state.finished = True
    pool = await get_pool()
    if state.db_run_id is not None:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE fetch_runs
                SET finished_at = NOW(),
                    fetched = $2,
                    added = $3,
                    skipped = $4,
                    errors = $5
                WHERE id = $1
                """,
                state.db_run_id,
                state.summary.get("fetched", 0),
                state.summary.get("added", 0),
                state.summary.get("skipped", 0),
                state.summary.get("errors", 0) + (1 if state.error else 0),
            )
    await _broadcast(state, json.dumps({"event": "closed"}))


# ─── persistence ──────────────────────────────────────────────────────────

async def _persist_videos(site: str, videos: list[dict]) -> int:
    if not videos:
        return 0
    pool = await get_pool()
    added = 0
    async with pool.acquire() as conn, conn.transaction():
        for v in videos:
            try:
                slug = _slugify(v.get("title") or "")
                if not slug:
                    continue
                row = await conn.fetchrow(
                    """
                    INSERT INTO videos (
                        site, source, source_url, embed_url, embed_type,
                        title, slug, thumbnail_url, preview_url, duration_seconds
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (site, source_url) DO NOTHING
                    RETURNING id
                    """,
                    site,
                    v.get("source"),
                    v.get("sourceUrl"),
                    v.get("embedUrl"),
                    v.get("embedType", "iframe"),
                    v.get("title"),
                    slug,
                    v.get("thumbnailUrl"),
                    v.get("previewUrl"),
                    v.get("durationSeconds"),
                )
                if row is not None:
                    added += 1
                    await _attach_terms(conn, int(row["id"]), v)
            except Exception:
                # Don't let one bad row poison the batch.
                continue
    return added


async def _attach_terms(conn, video_id: int, v: dict) -> None:
    for kind, table, join in (
        ("actors", "actors", "video_actors"),
        ("studios", "studios", "video_studios"),
        ("categories", "categories", "video_categories"),
    ):
        names = [str(n).strip() for n in (v.get(kind) or []) if str(n).strip()]
        for name in names:
            slug = _slugify(name)
            if not slug:
                continue
            term = await conn.fetchrow(
                f"""
                INSERT INTO {table} (name, slug)
                VALUES ($1, $2)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                name,
                slug,
            )
            await conn.execute(
                f"INSERT INTO {join} (video_id, {table[:-1]}_id) "
                f"VALUES ($1, $2) ON CONFLICT DO NOTHING",
                video_id,
                int(term["id"]),
            )


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    if not value:
        return ""
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalised = normalised.lower()
    normalised = _SLUG_RE.sub("-", normalised).strip("-")
    return normalised[:200]
