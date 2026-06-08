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
import platform
import re
import shutil
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional

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
    stderr_log: Optional[str] = None


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
    # Default: sibling repo layout - vaultwares-api/.. / Prom-King/shared-tube
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

    cwd = _shared_tube_path()
    args = [
        "--filter",
        "@promking/shared-tube",
        "fetcher:run",
        "--",
        f"--site={state.site}",
        f"--source={state.source}",
        f"--pages={state.pages}",
    ]

    # Platform-aware spawn. On Windows, pnpm ships as `pnpm.CMD` (a Corepack
    # shim); asyncio's create_subprocess_exec calls CreateProcess directly and
    # can't execute .CMD without going through cmd.exe — so we wrap. On Linux
    # the binary is plain `pnpm` and direct exec works.
    #
    # `limit` bumps asyncio StreamReader buffer from the 64 KiB default. The
    # CLI's `videos` event is a single JSON line carrying every fetched item;
    # a 3-page fullvideos run is ~60-100 KB and hits LimitOverrunError without
    # this. 10 MiB is generous (a single page is ~30 videos × ~500 bytes).
    is_windows = platform.system() == "Windows"
    PIPE_LIMIT = 10 * 1024 * 1024  # 10 MiB
    if is_windows:
        # Use shell=True style via create_subprocess_shell so cmd.exe resolves
        # pnpm.CMD against PATHEXT. Quote any path that might contain spaces.
        shell_cmd = "pnpm " + " ".join(f'"{a}"' if " " in a else a for a in args)
        try:
            proc = await asyncio.create_subprocess_shell(
                shell_cmd,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=PIPE_LIMIT,
            )
        except (FileNotFoundError, OSError) as e:
            state.error = f"failed to spawn pnpm (Windows shell): {e}"
            await _broadcast(state, json.dumps({"event": "error", "message": state.error}))
            await _finalize_run(state)
            return
    else:
        pnpm_path = shutil.which("pnpm") or "pnpm"
        try:
            proc = await asyncio.create_subprocess_exec(
                pnpm_path,
                *args,
                cwd=str(cwd),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=PIPE_LIMIT,
            )
        except FileNotFoundError as e:
            state.error = f"failed to spawn pnpm: {e}"
            await _broadcast(state, json.dumps({"event": "error", "message": state.error}))
            await _finalize_run(state)
            return

    state.process = proc

    assert proc.stdout is not None
    assert proc.stderr is not None

    videos_payload: list[dict] = []
    stderr_buf: list[str] = []

    async def _drain_stderr() -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            if not text:
                continue
            stderr_buf.append(text)
            # Surface stderr as log events so the operator sees it live.
            await _broadcast(state, json.dumps({"event": "log", "line": f"stderr: {text}"}))

    stderr_task = asyncio.create_task(_drain_stderr())

    while True:
        try:
            line = await proc.stdout.readline()
        except asyncio.LimitOverrunError as e:
            # A single CLI line exceeded the (already-raised) buffer cap.
            # Drain the rest of the line via read(e.consumed) so we don't
            # spin forever and surface the failure to the operator.
            state.error = f"CLI stdout line exceeded buffer: {e}"
            await _broadcast(
                state,
                json.dumps({"event": "error", "message": state.error}),
            )
            try:
                await proc.stdout.read(e.consumed)
            except Exception:
                pass
            break
        except ValueError as e:
            # Older asyncio raises ValueError for the same condition.
            state.error = f"CLI stdout read failed: {e}"
            await _broadcast(
                state,
                json.dumps({"event": "error", "message": state.error}),
            )
            break
        if not line:
            break
        text = line.decode("utf-8", errors="replace").rstrip("\n")
        if not text:
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
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
            # CLI now emits one `videos` line per item (each with a single-
            # element array) to stay under the asyncio StreamReader buffer.
            # Accumulate; the persistence loop handles the union at the end.
            chunk = payload.get("videos")
            if isinstance(chunk, list):
                videos_payload.extend(chunk)

    return_code = await proc.wait()
    try:
        await asyncio.wait_for(stderr_task, timeout=5)
    except asyncio.TimeoutError:
        stderr_task.cancel()

    if return_code != 0 and not state.error:
        tail = "\n".join(stderr_buf[-10:]) or "(no stderr captured)"
        state.error = f"fetcher exited with code {return_code}. stderr tail:\n{tail}"

    state.stderr_log = "\n".join(stderr_buf[-40:]) if stderr_buf else None

    # Persist whatever the CLI returned. The CLI itself never writes.
    try:
        added = await _persist_videos(state.site, videos_payload)
    except Exception as e:
        state.error = f"persist failed: {e}"
        added = 0
    state.summary["added"] = added
    # Tell the console the real post-persistence count — the CLI's `done`
    # event always emits added=0 by design (CLI never writes).
    await _broadcast(
        state,
        json.dumps({
            "event": "persisted",
            "summary": dict(state.summary),
            "candidates": len(videos_payload),
        }),
    )
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
        log_blob = {
            "error": state.error,
            "stderr_tail": state.stderr_log,
        }
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE fetch_runs
                SET finished_at = NOW(),
                    fetched = $2,
                    added = $3,
                    skipped = $4,
                    errors = $5,
                    log = $6::jsonb
                WHERE id = $1
                """,
                state.db_run_id,
                state.summary.get("fetched", 0),
                state.summary.get("added", 0),
                state.summary.get("skipped", 0),
                state.summary.get("errors", 0) + (1 if state.error else 0),
                json.dumps(log_blob),
            )
    await _broadcast(state, json.dumps({"event": "closed"}))


# ─── persistence ──────────────────────────────────────────────────────────

async def _persist_videos(site: str, videos: list[dict]) -> int:
    """
    Insert videos one at a time WITHOUT an outer transaction.

    Earlier this used `async with conn.transaction():` to wrap the whole
    batch, but Postgres aborts the whole transaction on any single failed
    statement (e.g. a NOT NULL violation on embed_url). asyncpg then makes
    every subsequent statement raise "current transaction is aborted",
    the inner try/except swallows them, and at the end the .transaction()
    context manager re-raises at commit — so the run finalisation never
    ran. Per-row autocommit is fine here: each INSERT is independently
    idempotent via ON CONFLICT (site, source_url) DO NOTHING.
    """
    if not videos:
        return 0
    pool = await get_pool()
    added = 0
    skipped_bad = 0
    async with pool.acquire() as conn:
        for v in videos:
            slug = _slugify(v.get("title") or "")
            if not slug:
                skipped_bad += 1
                continue
            # Pre-validate the NOT NULL columns before hitting Postgres.
            required = ("sourceUrl", "embedUrl", "title")
            if any(not v.get(k) for k in required):
                skipped_bad += 1
                continue
            try:
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
            except Exception:
                # Bad row — log it via skipped_bad, keep the run alive.
                skipped_bad += 1
                continue
            if row is None:
                # Duplicate (ON CONFLICT DO NOTHING). Not an error.
                continue
            added += 1
            try:
                await _attach_terms(conn, int(row["id"]), v)
            except Exception:
                # Term attachment failure shouldn't roll back the video.
                continue
    if skipped_bad:
        # Surface to logs so the operator can audit dropped rows.
        import logging
        logging.getLogger(__name__).info(
            "promking: persisted %d videos, skipped %d (validation/dup/error)",
            added, skipped_bad,
        )
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
