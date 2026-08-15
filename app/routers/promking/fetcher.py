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
import random
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, Optional
from pydantic import BaseModel

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import StreamingResponse

from .db import get_pool
from ._models import FetchRunHandle, FetchRunRequest, Site
from .tpdb import fetch_tpdb_tags

router = APIRouter(prefix="/fetcher", tags=["promking:fetcher"])


class CursorUpdateRequest(BaseModel):
    site: Site
    source: str
    page: int


# ─── Run registry (in-memory) ──────────────────────────────────────────────

@dataclass
class RunState:
    run_id: str
    site: str
    source: str
    pages: int
    start_page: Optional[int] = None
    # Term-scoped runs (studio/pornstar/category archive). These ignore the
    # manual cursor and walk the archive sequentially from page 1.
    term_type: Optional[str] = None
    term_name: Optional[str] = None
    term_slug: Optional[str] = None
    fetch_all: bool = False
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


async def _create_fetch_run_state(
    *,
    site: str,
    source: str,
    pages: int,
    start_page: Optional[int] = None,
    term_type: Optional[str] = None,
    term_name: Optional[str] = None,
    term_slug: Optional[str] = None,
    fetch_all: bool = False,
) -> tuple[RunState, datetime]:
    run_id = uuid.uuid4().hex
    state = RunState(
        run_id=run_id,
        site=site,
        source=source,
        pages=pages,
        start_page=start_page,
        term_type=term_type,
        term_name=term_name,
        term_slug=term_slug,
        fetch_all=fetch_all,
    )
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO fetch_runs (site, source, started_at, log)
            VALUES ($1, $2, NOW(), $3::jsonb)
            RETURNING id, started_at
            """,
            site,
            source,
            json.dumps({"query": term_name or term_slug or ""}),
        )
    state.db_run_id = int(row["id"])
    async with _runs_lock:
        _runs[run_id] = state
    return state, row["started_at"]


# ─── POST /fetcher/run ─────────────────────────────────────────────────────

@router.post("/cron/reload")
async def reload_cron_jobs() -> dict:
    """Re-read `settings.fetcher_cron` per site and rebuild the APScheduler
    job list. Called by the admin after saving a schedule so changes apply
    without an API restart."""
    try:
        from .cron import reload_jobs
        await reload_jobs()
        return {"ok": True}
    except Exception as exc:
        # Non-fatal: schedules will apply on next API restart anyway.
        return {"ok": False, "error": str(exc)}


@router.get("/cron/jobs")
async def list_cron_jobs() -> list[dict]:
    """
    List every scheduled fetcher job across all sites, with next-fire time
    (from APScheduler) and last-run status (from fetch_runs). The admin uses
    this to render a schedule dashboard without having to reload the tab.
    """
    from .cron import get_scheduled_jobs
    return await get_scheduled_jobs()


@router.get("/cursors")
async def get_all_cursors(site: Site = Query(...)) -> dict[str, int]:
    """Get current page cursor for each source on this site."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE site = $1 AND key = 'fetcher_manual_cursor'",
            site,
        )
    if row and row["value"]:
        val = json.loads(row["value"]) if isinstance(row["value"], str) else row["value"]
        if isinstance(val, dict):
            return {str(k): int(v) for k, v in val.items() if str(v).isdigit()}
    return {}


@router.put("/cursors")
async def set_cursor(payload: CursorUpdateRequest) -> dict:
    """Set the current page index for a source on this site."""
    if payload.page < 1:
        raise HTTPException(status_code=400, detail="Page must be at least 1")
    await update_manual_cursor(payload.site, payload.source, payload.page)
    return {"ok": True, "site": payload.site, "source": payload.source, "page": payload.page}


@router.post("/run", response_model=FetchRunHandle)
async def run_fetcher(req: FetchRunRequest, bg: BackgroundTasks) -> FetchRunHandle:
    state, started_at = await _create_fetch_run_state(
        site=req.site,
        source=req.source,
        pages=req.pages,
        start_page=getattr(req, "start_page", None),
        term_type=req.term_type,
        term_name=req.term_name,
        term_slug=req.term_slug,
        fetch_all=req.fetch_all,
    )

    # Spawn the subprocess in the background.
    bg.add_task(_drive_subprocess, state)
    return FetchRunHandle(
        run_id=state.run_id,
        site=req.site,
        source=req.source,
        pages=req.pages,
        started_at=started_at,
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
async def recent_runs(limit: int = 25, site: Site | None = Query(None)) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if site:
            rows = await conn.fetch(
                """
                SELECT id, site::text AS site, source, started_at, finished_at,
                       fetched, added, skipped, errors, log->>'query' AS query
                FROM fetch_runs
                WHERE site = $1
                ORDER BY started_at DESC
                LIMIT $2
                """,
                site,
                min(max(limit, 1), 200),
            )
        else:
            rows = await conn.fetch(
                """
                SELECT id, site::text AS site, source, started_at, finished_at,
                       fetched, added, skipped, errors, log->>'query' AS query
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


async def get_manual_cursor(site: str, source: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE site = $1 AND key = 'fetcher_manual_cursor'",
            site,
        )
    if row and row["value"]:
        val = json.loads(row["value"]) if isinstance(row["value"], str) else row["value"]
        if isinstance(val, dict):
            try:
                return int(val.get(source, 1))
            except Exception:
                pass
    return 1


async def update_manual_cursor(site: str, source: str, page: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn, conn.transaction():
        row = await conn.fetchrow(
            "SELECT value FROM settings WHERE site = $1 AND key = 'fetcher_manual_cursor'",
            site,
        )
        val = {}
        if row and row["value"]:
            # asyncpg's jsonb codec (db.py) decodes to native. Keep the
            # legacy string branch for defense against any un-migrated codec.
            val = json.loads(row["value"]) if isinstance(row["value"], str) else row["value"]
            if not isinstance(val, dict):
                val = {}
        val[source] = page

        await conn.execute(
            """
            INSERT INTO settings (site, key, value, updated_at)
            VALUES ($1::text::site, 'fetcher_manual_cursor', $2::jsonb, NOW())
            ON CONFLICT (site, key) DO UPDATE
              SET value = EXCLUDED.value,
                  updated_at = NOW()
            """,
            site,
            json.dumps(val),
        )


async def check_existing_links(site: str, links: list[str]) -> set[str]:
    """
    Which of `links` are already known to us on this site? Since the schema
    migration on 2026-07-04 videos are catalogued once and joined onto sites
    via `video_sites`, so we JOIN through that instead of filtering on a
    (now-removed) `videos.site` column.
    """
    if not links:
        return set()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT v.source_url
              FROM videos v
              JOIN video_sites vs ON vs.video_id = v.id
             WHERE vs.site = $1 AND v.source_url = ANY($2)
            """,
            site,
            links,
        )
    return {r["source_url"] for r in rows}


async def check_existing_slugs(slugs: list[str]) -> set[str]:
    """Check which of candidate slugs already exist in videos table."""
    if not slugs:
        return set()
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT slug FROM videos WHERE slug = ANY($1)",
            slugs,
        )
    return {r["slug"] for r in rows}


def filter_duplicate_candidates(
    candidates: list[dict],
    existing_urls: set[str],
    existing_slugs: set[str],
) -> list[dict]:
    """Filter candidates that are already in DB by sourceUrl or slug, or duplicate on the page."""
    unique_candidates = []
    seen_urls = set(existing_urls)
    seen_slugs = set(existing_slugs)

    for c in candidates:
        url = c.get("sourceUrl")
        slug = _slugify(c.get("title") or "")
        if not url or not slug:
            continue

        if url in seen_urls or slug in seen_slugs:
            continue

        seen_urls.add(url)
        seen_slugs.add(slug)
        unique_candidates.append(c)

    return unique_candidates


def _name_key(name: str) -> str:
    return " ".join(str(name).strip().lower().split())


def _unique_names(names: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in names:
        clean = str(name).strip()
        if not clean:
            continue
        key = _name_key(clean)
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _merge_validated_term_names(
    source_names: list[str],
    local_matches: dict[str, dict],
    tpdb_names: list[str],
) -> list[str]:
    """
    Keep exact local DB matches first, including old names that now point at a
    merged primary. Unmatched scraped names are not trusted unless TPDB returns
    them or a TPDB canonical replacement.
    """
    ordered: list[str] = []
    seen: set[str] = set()

    for name in _unique_names(source_names):
        match_data = local_matches.get(_name_key(name))
        if not match_data:
            continue
        canonical = match_data["name"]
        key = _name_key(canonical)
        if key not in seen:
            ordered.append(canonical)
            seen.add(key)

    for name in _unique_names(tpdb_names):
        key = _name_key(name)
        if key not in seen:
            ordered.append(name)
            seen.add(key)

    return ordered


async def _fetch_local_term_matches(conn, table: str, names: list[str]) -> dict[str, dict]:
    keys = [_name_key(name) for name in names if str(name).strip()]
    if not keys:
        return {}
    rows = await conn.fetch(
        f"""
        SELECT lower(match.name) AS source_key,
               COALESCE(primary_term.name, match.name) AS canonical_name,
               COALESCE(primary_term.disabled, match.disabled) AS disabled
          FROM {table} AS match
          LEFT JOIN {table} AS primary_term
            ON primary_term.id = match.merged_into_id
         WHERE lower(match.name) = ANY($1::text[])
           AND (match.deleted_at IS NULL OR match.merged_into_id IS NOT NULL)
        """,
        keys,
    )
    return {str(r["source_key"]): {"name": str(r["canonical_name"]), "disabled": bool(r["disabled"])} for r in rows}


async def _validate_video_terms(
    v: dict,
    pornstar_matches: dict[str, dict],
    studio_matches: dict[str, dict],
    category_matches: dict[str, dict],
) -> None:
    raw_pornstars = [str(n).strip() for n in (v.get("pornstars") or []) if str(n).strip()]
    raw_studios = [str(n).strip() for n in (v.get("studios") or []) if str(n).strip()]
    raw_categories = [str(n).strip() for n in (v.get("categories") or []) if str(n).strip()]

    source_pornstars: list[str] = []
    source_studios: list[str] = list(raw_studios)

    # Sub-studio check: if a scraped "pornstar" pill matches an existing studio in DB, treat as studio
    for name in raw_pornstars:
        name_k = _name_key(name)
        if name_k in studio_matches:
            source_studios.append(name)
        else:
            source_pornstars.append(name)

    exact_pornstars = _merge_validated_term_names(source_pornstars, pornstar_matches, [])
    exact_studios = _merge_validated_term_names(source_studios, studio_matches, [])
    needs_tpdb = (
        len(exact_pornstars) < len(_unique_names(source_pornstars))
        or len(exact_studios) < len(_unique_names(source_studios))
        or (not source_pornstars and not source_studios)
    )

    tpdb_data = await fetch_tpdb_tags(v.get("title")) if needs_tpdb else None
    tpdb_pornstars = tpdb_data["performers"] if tpdb_data else []
    tpdb_studios = tpdb_data["studios"] if tpdb_data else []

    v["pornstars"] = _merge_validated_term_names(source_pornstars, pornstar_matches, tpdb_pornstars)
    v["studios"] = _merge_validated_term_names(source_studios, studio_matches, tpdb_studios)
    if tpdb_data:
        v["categories"] = _unique_names(tpdb_data["categories"])
        v["_scene"] = tpdb_data.get("_scene")

    is_disabled = False
    for name in _unique_names(source_pornstars):
        match_data = pornstar_matches.get(_name_key(name))
        if match_data and match_data.get("disabled"):
            is_disabled = True
            break
    if not is_disabled:
        for name in _unique_names(source_studios):
            match_data = studio_matches.get(_name_key(name))
            if match_data and match_data.get("disabled"):
                is_disabled = True
                break
    if not is_disabled:
        all_cat_names = _unique_names(raw_categories + (v.get("categories") or []))
        for name in all_cat_names:
            match_data = category_matches.get(_name_key(name))
            if match_data and match_data.get("disabled"):
                is_disabled = True
                break
    if is_disabled:
        v["_disabled"] = True


async def _run_subprocess_for_page(
    state: RunState, page_num: int
) -> tuple[list[dict], dict | None]:
    cli = _shared_tube_path() / "shared" / "src" / "fetcher" / "cli.ts"
    if not cli.exists():
        raise FileNotFoundError(f"fetcher CLI not found at {cli}")

    cwd = _shared_tube_path()
    args = [
        "--filter",
        "@promking/shared-tube",
        "fetcher:run",
        "--",
        f"--site={state.site}",
        f"--source={state.source}",
        "--pages=1",
        f"--startPage={page_num}",
    ]
    if state.term_type:
        args.append(f"--termType={state.term_type}")
        if state.term_name:
            args.append(f"--termName={state.term_name}")
        if state.term_slug:
            args.append(f"--termSlug={state.term_slug}")

    is_windows = platform.system() == "Windows"
    PIPE_LIMIT = 10 * 1024 * 1024  # 10 MiB
    if is_windows:
        shell_cmd = "pnpm " + " ".join(f'"{a}"' if " " in a else a for a in args)
        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=PIPE_LIMIT,
        )
    else:
        pnpm_path = shutil.which("pnpm") or "pnpm"
        proc = await asyncio.create_subprocess_exec(
            pnpm_path,
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=PIPE_LIMIT,
        )

    state.process = proc
    assert proc.stdout is not None
    assert proc.stderr is not None

    videos = []
    listing_meta: dict | None = None
    stderr_buf = []

    async def _drain_stderr() -> None:
        assert proc.stderr is not None
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            if text:
                stderr_buf.append(text)
                await _broadcast(state, json.dumps({"event": "log", "line": f"stderr (page {page_num}): {text}"}))

    stderr_task = asyncio.create_task(_drain_stderr())

    while True:
        try:
            line = await proc.stdout.readline()
        except (asyncio.LimitOverrunError, ValueError) as e:
            await _broadcast(state, json.dumps({"event": "error", "message": f"CLI stdout read failed: {e}"}))
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
        
        event = payload.get("event")
        if event == "log":
            log_line = f"[Page {page_num}] {payload.get('line', '')}"
            await _broadcast(state, json.dumps({"event": "log", "line": log_line}))
        elif event == "videos":
            chunk = payload.get("videos")
            if isinstance(chunk, list):
                videos.extend(chunk)
        elif event == "listing_meta":
            # First-page-only signal from the CLI: how many items the source
            # says the archive contains. Used by _drive_term_run to cap
            # pagination on sources (pornxp) that keep serving unrelated
            # content past the real end.
            total = payload.get("totalItems")
            page_size = payload.get("pageSize")
            listing_meta = {
                "total_items": int(total) if isinstance(total, (int, float)) else None,
                "page_size": int(page_size) if isinstance(page_size, (int, float)) else None,
            }

    return_code = await proc.wait()
    try:
        await asyncio.wait_for(stderr_task, timeout=5)
    except asyncio.TimeoutError:
        stderr_task.cancel()

    if return_code != 0:
        tail = "\n".join(stderr_buf[-10:]) or "(no stderr)"
        raise RuntimeError(f"fetcher exited with code {return_code}. stderr tail: {tail}")

    return videos, listing_meta


async def _drive_term_run(state: RunState) -> None:
    """
    Term-scoped run: walk the archive (studio/pornstar/category) sequentially
    from page 1. Ignores the manual cursor entirely — archives are small and
    ordered, so random offsets and duplicate-zone heuristics don't apply.
    Stops on the first empty page, after `pages` pages (unless fetch_all),
    when two consecutive pages return only rows already in the DB, or at the
    safety cap. Progress is broadcast per page so the admin can see it.
    """
    try:
        label = f"{state.term_type}:{state.term_name or state.term_slug}"
        MAX_SAFETY_PAGES = 30
        page_budget = MAX_SAFETY_PAGES if state.fetch_all else min(state.pages, MAX_SAFETY_PAGES)
        target = f"up to {page_budget} page(s)"
        await _broadcast(state, json.dumps({"event": "log", "line": f"▶ Term fetch {label} on {state.source} — {target}, cursor ignored."}))

        fetched_urls: set[str] = set()
        current_page = 1
        consecutive_all_known_pages = 0
        source_declared_pages: Optional[int] = None
        state.summary = {"fetched": 0, "added": 0, "skipped": 0, "errors": 0}

        while current_page <= page_budget:
            await _broadcast(state, json.dumps({"event": "log", "line": f"--- Fetching Page {current_page}/{page_budget} ---"}))
            try:
                page_videos, listing_meta = await _run_subprocess_for_page(state, current_page)
            except Exception as e:
                state.error = f"Subprocess failed on page {current_page}: {e}"
                await _broadcast(state, json.dumps({"event": "error", "message": state.error}))
                break

            if listing_meta and source_declared_pages is None:
                total = listing_meta.get("total_items")
                page_size = listing_meta.get("page_size") or len(page_videos) or 36
                if total and page_size:
                    source_declared_pages = max(1, (total + page_size - 1) // page_size)
                    new_budget = min(page_budget, source_declared_pages)
                    if new_budget < page_budget:
                        await _broadcast(state, json.dumps({"event": "log", "line": f"📐 Source declares {total} videos / {page_size} per page → capping at {source_declared_pages} page(s)."}))
                        page_budget = new_budget

            if not page_videos:
                await _broadcast(state, json.dumps({"event": "log", "line": f"Page {current_page} returned 0 videos — end of archive."}))
                break

            page_new_urls: list[str] = []
            page_candidates: list[dict] = []
            for v in page_videos:
                url = v.get("sourceUrl")
                if url and url not in fetched_urls:
                    fetched_urls.add(url)
                    page_candidates.append(v)
                    page_new_urls.append(url)
            if not page_new_urls:
                await _broadcast(state, json.dumps({"event": "log", "line": f"Page {current_page} repeated earlier items — end of archive."}))
                break

            existing_on_page = await check_existing_links(state.site, page_new_urls)
            unknown_on_page = len(page_new_urls) - len(existing_on_page)
            await _broadcast(state, json.dumps({"event": "log", "line": f"Page {current_page}: {unknown_on_page} new / {len(existing_on_page)} already in DB (of {len(page_new_urls)})"}))
            
            if unknown_on_page == 0:
                consecutive_all_known_pages += 1
                state.summary["fetched"] += len(page_videos)
                state.summary["skipped"] += len(page_videos)
                if consecutive_all_known_pages >= 2:
                    await _broadcast(state, json.dumps({"event": "log", "line": f"⚠️ 2 consecutive all-known pages — stopping."}))
                    break
            else:
                consecutive_all_known_pages = 0
                candidates_to_persist = [v for v in page_candidates if v.get("sourceUrl") not in existing_on_page]
                candidate_slugs = [_slugify(v.get("title") or "") for v in candidates_to_persist if v.get("title")]
                existing_slugs = await check_existing_slugs(candidate_slugs)
                filtered_candidates = filter_duplicate_candidates(candidates_to_persist, existing_on_page, existing_slugs)
                
                added_this_page, disabled_this_page = await _persist_videos(state.site, filtered_candidates)
                skipped_this_page = len(page_videos) - added_this_page

                state.summary["fetched"] += len(page_videos)
                state.summary["added"] += added_this_page
                state.summary["skipped"] += skipped_this_page

                await _broadcast(
                    state,
                    json.dumps({
                        "event": "persisted",
                        "summary": dict(state.summary),
                        "candidates": len(filtered_candidates),
                    }),
                )
            current_page += 1

    except Exception as e:
        state.error = f"Term run driver error: {e}"
        await _broadcast(state, json.dumps({"event": "error", "message": state.error}))
    finally:
        await _finalize_run(state)


async def _drive_subprocess(state: RunState) -> None:
    if state.term_type:
        await _drive_term_run(state)
        return
    try:
        start_page = state.start_page if hasattr(state, "start_page") and state.start_page is not None else await get_manual_cursor(state.site, state.source)
        current_page = max(1, start_page)
        
        await _broadcast(state, json.dumps({"event": "log", "line": f"▶ Fetching {state.source} on {state.site} starting at page {current_page} (target: {state.pages} page(s))"}))
        
        pages_counted = 0
        fetched_urls = set()
        
        state.summary = {"fetched": 0, "added": 0, "skipped": 0, "errors": 0}

        MAX_SAFETY_PAGES = 500
        total_pages_fetched = 0
        
        while pages_counted < state.pages and total_pages_fetched < MAX_SAFETY_PAGES:
            await _broadcast(state, json.dumps({"event": "log", "line": f"--- Fetching Page {current_page} (Counted: {pages_counted}/{state.pages} pages, Scanned: {total_pages_fetched}) ---"}))
            try:
                page_videos, _meta = await _run_subprocess_for_page(state, current_page)
            except Exception as e:
                state.error = f"Subprocess failed on page {current_page}: {e}"
                await _broadcast(state, json.dumps({"event": "error", "message": state.error}))
                break
                
            total_pages_fetched += 1
            if not page_videos:
                await _broadcast(state, json.dumps({"event": "log", "line": f"Page {current_page} returned 0 videos. Stopping."}))
                break

            state.summary["fetched"] += len(page_videos)
                
            unique_page_videos = []
            for v in page_videos:
                url = v.get("sourceUrl")
                if url and url not in fetched_urls:
                    fetched_urls.add(url)
                    unique_page_videos.append(v)
            
            if not unique_page_videos:
                state.summary["skipped"] += len(page_videos)
                await _broadcast(state, json.dumps({"event": "log", "line": f"All videos on page {current_page} were already processed in this run."}))
                current_page += 1
                continue

            urls_to_check = [v["sourceUrl"] for v in unique_page_videos if v.get("sourceUrl")]
            existing_urls = await check_existing_links(state.site, urls_to_check)
            
            new_candidates = [v for v in unique_page_videos if v.get("sourceUrl") not in existing_urls]

            if not new_candidates:
                state.summary["skipped"] += len(page_videos)
                await _broadcast(state, json.dumps({"event": "log", "line": f"Page {current_page}: all {len(unique_page_videos)} videos already in DB."}))
            else:
                candidate_slugs = [_slugify(v.get("title") or "") for v in new_candidates if v.get("title")]
                existing_slugs = await check_existing_slugs(candidate_slugs)
                filtered_candidates = filter_duplicate_candidates(new_candidates, existing_urls, existing_slugs)
                
                added_this_page, disabled_this_page = await _persist_videos(state.site, filtered_candidates)
                
                skipped_this_page = len(page_videos) - added_this_page
                state.summary["added"] += added_this_page
                state.summary["skipped"] += skipped_this_page

                await _broadcast(
                    state,
                    json.dumps({
                        "event": "persisted",
                        "summary": dict(state.summary),
                        "candidates": len(filtered_candidates),
                    }),
                )

                if added_this_page > 0:
                    pages_counted += 1
                    await _broadcast(state, json.dumps({"event": "log", "line": f"✨ Page {current_page}: +{added_this_page} active videos added to DB ({disabled_this_page} disabled). ({pages_counted}/{state.pages} counted pages)"}))
                else:
                    await _broadcast(state, json.dumps({"event": "log", "line": f"Page {current_page}: 0 active videos added (filtered out as duplicates or disabled terms)."}))

            current_page += 1
            
        await update_manual_cursor(state.site, state.source, current_page)
        await _broadcast(state, json.dumps({"event": "log", "line": f"💾 Saved next cursor page P = {current_page} in DB settings."}))
        
    except Exception as e:
        state.error = f"Subprocess driver error: {e}"
        await _broadcast(state, json.dumps({"event": "error", "message": state.error}))
    finally:
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
            "query": state.term_name or state.term_slug or "",
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
                    log = $6
                WHERE id = $1
                """,
                state.db_run_id,
                state.summary.get("fetched", 0),
                state.summary.get("added", 0),
                state.summary.get("skipped", 0),
                state.summary.get("errors", 0) + (1 if state.error else 0),
                log_blob,
            )
    await _broadcast(state, json.dumps({"event": "closed"}))


# ─── persistence ──────────────────────────────────────────────────────────

async def _persist_videos(site: str, videos: list[dict]) -> tuple[int, int]:
    """
    Insert videos one at a time WITHOUT an outer transaction.
    Returns (active_added_count, disabled_skipped_count).
    """
    if not videos:
        return 0, 0
        
    pool = await get_pool()
    added = 0
    disabled_skipped = 0
    skipped_bad = 0
    async with pool.acquire() as conn:
        validation_inputs: list[tuple[dict[str, dict], dict[str, dict], dict[str, dict]]] = []
        for v in videos:
            all_names = list(set((v.get("pornstars") or []) + (v.get("studios") or []) + (v.get("categories") or [])))
            pornstar_matches = await _fetch_local_term_matches(conn, "pornstars", all_names)
            studio_matches = await _fetch_local_term_matches(conn, "studios", all_names)
            category_matches = await _fetch_local_term_matches(conn, "categories", all_names)
            validation_inputs.append((pornstar_matches, studio_matches, category_matches))

    tpdb_sem = asyncio.Semaphore(8)

    async def _validate_with_limit(v: dict, pornstar_matches: dict[str, dict], studio_matches: dict[str, dict], category_matches: dict[str, dict]) -> None:
        async with tpdb_sem:
            await _validate_video_terms(v, pornstar_matches, studio_matches, category_matches)

    await asyncio.gather(
        *(
            _validate_with_limit(v, actor_matches, studio_matches, category_matches)
            for v, (actor_matches, studio_matches, category_matches) in zip(videos, validation_inputs)
        )
    )

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
            # asyncpg's jsonb codec (db.py) encodes the dict/list directly;
            # no more json.dumps here. Kept the guard against non-serialisable
            # scrape values.
            qualities = v.get("qualities") if v.get("qualities") else None
            # Views from the scrape (may be None). Coerce to int; missing or
            # non-numeric drops to 0 so the NOT NULL DEFAULT 0 column holds.
            raw_views = v.get("views")
            try:
                views = int(raw_views) if raw_views is not None else 0
            except (TypeError, ValueError):
                views = 0
            description = v.get("description")
            if description is not None and not isinstance(description, str):
                description = str(description)

            is_video_disabled = bool(v.get("_disabled"))

            try:
                row = await conn.fetchrow(
                    """
                    INSERT INTO videos (
                        source, source_url, embed_url, embed_type,
                        title, slug, thumbnail_url, preview_url, duration_seconds,
                        views, description, qualities, disabled_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (source_url) DO UPDATE SET updated_at = now()
                    RETURNING id, (xmax = 0) AS inserted
                    """,
                    v.get("source"),
                    v.get("sourceUrl"),
                    v.get("embedUrl"),
                    v.get("embedType", "mp4"),
                    v.get("title"),
                    slug,
                    v.get("thumbnailUrl"),
                    v.get("previewUrl"),
                    v.get("durationSeconds"),
                    views,
                    description,
                    qualities,
                    "now" if is_video_disabled else None,
                )
            except Exception as e:
                if "videos_slug_uniq" in str(e) or "slug" in str(e).lower():
                    disambiguated_slug = f"{slug[:70]}-{uuid.uuid4().hex[:6]}"
                    try:
                        row = await conn.fetchrow(
                            """
                            INSERT INTO videos (
                                source, source_url, embed_url, embed_type,
                                title, slug, thumbnail_url, preview_url, duration_seconds,
                                views, description, qualities, disabled_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                            ON CONFLICT (source_url) DO UPDATE SET updated_at = now()
                            RETURNING id, (xmax = 0) AS inserted
                            """,
                            v.get("source"),
                            v.get("sourceUrl"),
                            v.get("embedUrl"),
                            v.get("embedType", "mp4"),
                            v.get("title"),
                            disambiguated_slug,
                            v.get("thumbnailUrl"),
                            v.get("previewUrl"),
                            v.get("durationSeconds"),
                            views,
                            description,
                            qualities,
                            "now" if is_video_disabled else None,
                        )
                    except Exception:
                        skipped_bad += 1
                        continue
                else:
                    skipped_bad += 1
                    continue
                
            if not row:
                skipped_bad += 1
                continue
                
            video_id = int(row["id"])
            if row["inserted"]:
                if not is_video_disabled:
                    added += 1
                else:
                    disabled_skipped += 1

            # Insert into video_sites to track many-to-many relationship
            await conn.execute(
                """
                INSERT INTO video_sites (video_id, site)
                VALUES ($1, $2)
                ON CONFLICT (video_id, site) DO NOTHING
                """,
                video_id,
                site,
            )
            
            # TPDB enrichment is now done concurrently before this loop
            
            try:
                await _attach_terms(conn, int(row["id"]), v)
            except Exception:
                # Term attachment failure shouldn't roll back the video.
                pass

            # Persist raw TPDB scene linked to this video
            scene = v.get("_scene")
            if scene:
                try:
                    import json as _json
                    tpdb_id = str(scene.get("id") or "")
                    if tpdb_id:
                        await conn.execute(
                            """
                            INSERT INTO tpdb_scenes (tpdb_id, title, video_id, data)
                            VALUES ($1, $2, $3, $4)
                            ON CONFLICT (tpdb_id) DO UPDATE
                              SET data = EXCLUDED.data,
                                  title = EXCLUDED.title,
                                  video_id = COALESCE(tpdb_scenes.video_id, EXCLUDED.video_id)
                            """,
                            tpdb_id,
                            v.get("title", ""),
                            video_id,
                            _json.dumps(scene),
                        )
                except Exception as e:
                    import logging as _log
                    _log.getLogger(__name__).warning("Failed to persist TPDB scene for video %d: %s", video_id, e)
    if skipped_bad:
        # Surface to logs so the operator can audit dropped rows.
        import logging
        logging.getLogger(__name__).info(
            "promking: persisted %d videos, skipped %d (validation/dup/error)",
            added, skipped_bad,
        )
    return added, disabled_skipped


async def _attach_terms(conn, video_id: int, v: dict) -> None:
    for kind, table, join, term_column in (
        ("pornstars", "pornstars", "video_pornstars", "pornstar_id"),
        ("studios", "studios", "video_studios", "studio_id"),
        ("categories", "categories", "video_categories", "category_id"),
    ):
        names = [str(n).strip() for n in (v.get(kind) or []) if str(n).strip()]
        for name in names:
            slug = _slugify(name)
            if not slug:
                continue
            term = await conn.fetchrow(
                f"""
                SELECT COALESCE(primary_term.id, {table}.id) AS id
                  FROM {table}
                  LEFT JOIN {table} AS primary_term
                    ON primary_term.id = {table}.merged_into_id
                 WHERE ({table}.slug = $1 OR lower({table}.name) = lower($2))
                   AND ({table}.deleted_at IS NULL OR {table}.merged_into_id IS NOT NULL)
                 ORDER BY ({table}.deleted_at IS NULL) DESC
                 LIMIT 1
                """,
                slug,
                name,
            )
            if not term:
                term = await conn.fetchrow(
                    f"""
                    INSERT INTO {table} (name, slug)
                    VALUES ($1, $2)
                    ON CONFLICT (slug) DO UPDATE
                       SET name = EXCLUDED.name
                     WHERE {table}.deleted_at IS NULL
                    RETURNING id
                    """,
                    name,
                    slug,
                )
            if not term:
                continue
            await conn.execute(
                f"INSERT INTO {join} (video_id, {term_column})"
                " VALUES ($1, $2) ON CONFLICT DO NOTHING",
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
