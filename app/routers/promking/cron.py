"""
APScheduler-driven nightly fetch.

Replaces the ADR-001 plan of node-cron because the router lives on the FastAPI
side. Deviation is documented in the ADR's 'Implementation deviations' section.

Schedule is set per (site, source) in the `settings` table under key
'fetcher_cron'. Example value (JSONB):
  { "enabled": true, "hour": 3, "minute": 17, "pages": 3 }

Each enabled (site, source) pair fires _drive_subprocess at the cron time.
The scheduler is started/stopped by `api_server.py` lifespan hooks.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .db import get_pool
from .fetcher import RunState, _drive_subprocess, _runs, _runs_lock
import uuid

log = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


async def start_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.start()
    await _reload_jobs()
    log.info("promking APScheduler started")


async def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


async def _reload_jobs() -> None:
    """Read fetcher_cron settings rows and replace all jobs."""
    if _scheduler is None:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT site::text AS site, value FROM settings WHERE key = 'fetcher_cron'"
        )

    _scheduler.remove_all_jobs()

    for row in rows:
        cfg = row["value"]
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except json.JSONDecodeError:
                continue
        if not isinstance(cfg, dict):
            continue
        # cfg shape: { "schedules": [{ "source": "pornxp", "hour": 3, "minute": 17,
        #                              "pages": 3, "enabled": true }, ... ] }
        for entry in cfg.get("schedules", []) or []:
            if not entry.get("enabled"):
                continue
            source = str(entry.get("source") or "").strip()
            if not source:
                continue
            hour = int(entry.get("hour", 3))
            minute = int(entry.get("minute", 0))
            pages = max(1, min(int(entry.get("pages", 3)), 100))
            site = row["site"]
            _scheduler.add_job(
                _scheduled_run,
                CronTrigger(hour=hour, minute=minute),
                args=[site, source, pages],
                id=f"promking:{site}:{source}",
                replace_existing=True,
            )
    log.info("promking APScheduler jobs reloaded: %d", len(_scheduler.get_jobs()))


async def _scheduled_run(site: str, source: str, pages: int) -> None:
    """Kick off a fetch run with no SSE subscriber — pure background."""
    run_id = uuid.uuid4().hex
    state = RunState(run_id=run_id, site=site, source=source, pages=pages)
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO fetch_runs (site, source, started_at) "
            "VALUES ($1, $2, NOW()) RETURNING id",
            site,
            source,
        )
    state.db_run_id = int(row["id"])
    async with _runs_lock:
        _runs[run_id] = state
    await _drive_subprocess(state)


async def reload_jobs() -> None:
    """Re-read settings and rebuild the job set. Call after a PUT /settings."""
    await _reload_jobs()
