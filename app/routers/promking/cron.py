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
from .fetcher import _create_fetch_run_state, _drive_subprocess, get_manual_cursor

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
    cursor = await get_manual_cursor(site, source)
    state, _started_at = await _create_fetch_run_state(
        site=site,
        source=source,
        pages=pages,
        start_page=cursor,
    )
    await _drive_subprocess(state)


async def reload_jobs() -> None:
    """Re-read settings and rebuild the job set. Call after a PUT /settings."""
    await _reload_jobs()


async def get_scheduled_jobs() -> list[dict]:
    """
    Snapshot of the current APScheduler job list, joined with the last-run
    row from `fetch_runs` for the same (site, source) so the admin can render
    a full schedule status without a second round-trip.
    """
    jobs_info: list[dict] = []
    if _scheduler is not None:
        for job in _scheduler.get_jobs():
            # Job id format: promking:{site}:{source}
            parts = job.id.split(":", 2)
            if len(parts) != 3 or parts[0] != "promking":
                continue
            _, site, source = parts
            next_run = job.next_run_time.isoformat() if job.next_run_time else None
            # Extract cron hour/minute from the trigger for display.
            hour_field = None
            minute_field = None
            try:
                for field in job.trigger.fields:  # type: ignore[attr-defined]
                    if field.name == "hour":
                        hour_field = str(field)
                    elif field.name == "minute":
                        minute_field = str(field)
            except Exception:
                pass
            pages = None
            try:
                pages = int(job.args[2]) if len(job.args) >= 3 else None
            except Exception:
                pass
            jobs_info.append({
                "site": site,
                "source": source,
                "hour": hour_field,
                "minute": minute_field,
                "pages": pages,
                "next_run_at": next_run,
            })
    # Attach the most-recent fetch_runs row per (site, source) for last-run
    # status. One query covers every job.
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (site, source)
                   site::text AS site, source, started_at, finished_at,
                   fetched, added, skipped, errors
              FROM fetch_runs
             ORDER BY site, source, started_at DESC
            """
        )
    last_by_key: dict[tuple[str, str], dict] = {
        (r["site"], r["source"]): {
            "started_at": r["started_at"].isoformat() if r["started_at"] else None,
            "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
            "fetched": r["fetched"],
            "added": r["added"],
            "skipped": r["skipped"],
            "errors": r["errors"],
        }
        for r in rows
    }
    for info in jobs_info:
        info["last_run"] = last_by_key.get((info["site"], info["source"]))
    return jobs_info
