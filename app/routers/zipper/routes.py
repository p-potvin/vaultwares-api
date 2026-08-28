"""Zipper API — jobs, site profiles, history, quotas.

Two clients:
  * the **extension**, which submits work and reads state;
  * the **worker** on the workstation, which claims jobs and reports progress.

The worker claims rather than being pushed to, so the workstation can be off and
the queue simply waits — today those jobs would just fail. This mirrors the
existing faceswap job flow in api/routes_jobs.py rather than inventing a second
convention.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import require_auth
from . import db

router = APIRouter(prefix="/api/zipper", tags=["zipper"])

# A claim older than this is assumed dead and returned to the queue. Without it
# a worker that dies mid-job strands that job forever.
CLAIM_STALE_SECONDS = 900


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- models ----

class JobCreate(BaseModel):
    kind: str = Field(default="batch", description="batch | stream | handoff")
    page_url: Optional[str] = None
    page_domain: Optional[str] = None
    title: Optional[str] = None
    route: Optional[str] = None
    links: List[str] = Field(default_factory=list)
    link_kinds: Dict[str, str] = Field(default_factory=dict)
    headers: Dict[str, str] = Field(default_factory=dict)
    options: Dict[str, Any] = Field(default_factory=dict)


class JobProgress(BaseModel):
    status: Optional[str] = None
    processed_links: Optional[int] = None
    total_links: Optional[int] = None
    bytes_done: Optional[int] = None
    bytes_total: Optional[int] = None
    progress: Optional[float] = None
    speed: Optional[int] = None
    eta: Optional[int] = None
    archives: Optional[List[str]] = None
    save_dir: Optional[str] = None
    error: Optional[str] = None


class ClaimRequest(BaseModel):
    worker: str
    kinds: List[str] = Field(default_factory=lambda: ["batch", "stream"])


class GrabRecord(BaseModel):
    """One file actually taken. Doubles as the profile's training signal."""
    domain: str
    url: str
    url_key: str
    asset_host: Optional[str] = None
    page_url: Optional[str] = None
    page_title: Optional[str] = None
    kind: Optional[str] = None
    mime: Optional[str] = None
    bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    origin: Optional[str] = None
    score: Optional[int] = None
    saved_as: Optional[str] = None
    route: Optional[str] = None
    outcome: str = "ok"
    accepted: bool = True
    duration_ms: Optional[int] = None
    speed: Optional[int] = None
    job_id: Optional[str] = None


class ProfilePatch(BaseModel):
    accepted_patterns: Optional[List[str]] = None
    rejected_patterns: Optional[List[str]] = None
    learned_upgrades: Optional[List[Dict[str, Any]]] = None
    best_origin: Optional[str] = None
    title_source: Optional[str] = None
    default_route: Optional[str] = None
    default_scope: Optional[str] = None
    needs_scroll: Optional[bool] = None
    connection_policy: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    last_full_count: Optional[int] = None
    last_fast_count: Optional[int] = None
    mark_full_scan: bool = False


class QuotaSpend(BaseModel):
    provider: str
    grabs: int = 1
    bytes: int = 0


# ------------------------------------------------------------------ jobs ----

@router.post("/jobs")
async def create_job(body: JobCreate, principal=Depends(require_auth)):
    job_id = f"z-{uuid.uuid4().hex[:12]}"
    await db.execute(
        """
        INSERT INTO zipper.jobs
            (id, kind, status, page_url, page_domain, title, route,
             links, link_kinds, headers, options, total_links)
        VALUES ($1,$2,'queued',$3,$4,$5,$6,$7,$8,$9,$10,$11)
        """,
        job_id, body.kind, body.page_url, body.page_domain, body.title, body.route,
        body.links, body.link_kinds, body.headers, body.options, len(body.links),
    )
    return {"ok": True, "job_id": job_id}


@router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(default=50, le=500),
    principal=Depends(require_auth),
):
    if status:
        rows = await db.fetch(
            "SELECT * FROM zipper.jobs WHERE status = $1 ORDER BY created_at DESC LIMIT $2",
            status, limit,
        )
    else:
        rows = await db.fetch(
            "SELECT * FROM zipper.jobs ORDER BY created_at DESC LIMIT $1", limit,
        )
    return {"ok": True, "jobs": [db.row_to_dict(r) for r in rows]}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, principal=Depends(require_auth)):
    row = await db.fetchrow("SELECT * FROM zipper.jobs WHERE id = $1", job_id)
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job": db.row_to_dict(row)}


@router.post("/jobs/claim")
async def claim_job(body: ClaimRequest, principal=Depends(require_auth)):
    """Hand the oldest queued job to a worker.

    The UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) is what makes
    this safe with more than one worker: two simultaneous claims take different
    rows instead of both winning the same one.

    The same statement also reclaims jobs whose worker went away mid-flight,
    which is why the stale check sits in the subquery rather than in a separate
    sweep — a job nobody is working must not sit 'claimed' forever.
    """
    rows = await db.fetch(
        """
        UPDATE zipper.jobs SET
            status = 'claimed',
            claimed_by = $1,
            claimed_at = now(),
            heartbeat_at = now()
        WHERE id IN (
            SELECT id FROM zipper.jobs
            WHERE kind = ANY($2::text[])
              AND (
                    status = 'queued'
                 OR (status IN ('claimed','running')
                     AND heartbeat_at < now() - ($3 || ' seconds')::interval)
              )
            ORDER BY created_at
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING *
        """,
        body.worker, body.kinds, str(CLAIM_STALE_SECONDS),
    )
    if not rows:
        return {"ok": True, "job": None}
    return {"ok": True, "job": db.row_to_dict(rows[0])}


@router.post("/jobs/{job_id}/progress")
async def update_progress(job_id: str, body: JobProgress, principal=Depends(require_auth)):
    sets, args = [], []

    def put(col: str, val: Any) -> None:
        args.append(val)
        sets.append(f"{col} = ${len(args)}")

    for col in ("status", "processed_links", "total_links", "bytes_done",
                "bytes_total", "progress", "speed", "eta", "save_dir", "error"):
        val = getattr(body, col)
        if val is not None:
            put(col, val)
    if body.archives is not None:
        put("archives", body.archives)

    # Any progress report is also a heartbeat — that is what stops a long but
    # healthy job from being reclaimed out from under its worker.
    sets.append("heartbeat_at = now()")
    if body.status in ("completed", "failed", "aborted"):
        sets.append("finished_at = now()")

    args.append(job_id)
    await db.execute(
        f"UPDATE zipper.jobs SET {', '.join(sets)} WHERE id = ${len(args)}", *args,
    )
    return {"ok": True}


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, principal=Depends(require_auth)):
    await db.execute("DELETE FROM zipper.jobs WHERE id = $1", job_id)
    return {"ok": True}


# --------------------------------------------------------------- history ----

@router.post("/history")
async def record_grabs(body: List[GrabRecord], principal=Depends(require_auth)):
    """Record what was actually taken.

    Upserts on (domain, url_key) so re-grabbing the same asset updates rather
    than duplicating — which is what makes "have I already got this?" a single
    indexed lookup instead of a scan.
    """
    if not body:
        return {"ok": True, "recorded": 0}
    for g in body:
        await db.execute(
            """
            INSERT INTO zipper.history
                (job_id, domain, asset_host, page_url, page_title, url, url_key,
                 kind, mime, bytes, width, height, origin, score,
                 saved_as, route, outcome, accepted, duration_ms, speed)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20)
            ON CONFLICT (domain, url_key) DO UPDATE SET
                ts = now(),
                saved_as = EXCLUDED.saved_as,
                outcome  = EXCLUDED.outcome,
                accepted = EXCLUDED.accepted,
                route    = EXCLUDED.route,
                bytes    = COALESCE(EXCLUDED.bytes, history.bytes)
            """,
            g.job_id, g.domain, g.asset_host, g.page_url, g.page_title, g.url, g.url_key,
            g.kind, g.mime, g.bytes, g.width, g.height, g.origin, g.score,
            g.saved_as, g.route, g.outcome, g.accepted, g.duration_ms, g.speed,
        )
    return {"ok": True, "recorded": len(body)}


@router.post("/history/lookup")
async def lookup_grabs(
    body: Dict[str, Any],
    principal=Depends(require_auth),
):
    """Which of these url_keys do we already have, and under what filename."""
    keys: List[str] = body.get("url_keys") or []
    domain: Optional[str] = body.get("domain")
    if not keys:
        return {"ok": True, "grabbed": {}}
    if domain:
        rows = await db.fetch(
            "SELECT url_key, saved_as FROM zipper.history "
            "WHERE domain = $1 AND url_key = ANY($2::text[]) AND accepted",
            domain, keys,
        )
    else:
        rows = await db.fetch(
            "SELECT url_key, saved_as FROM zipper.history "
            "WHERE url_key = ANY($1::text[]) AND accepted", keys,
        )
    return {"ok": True, "grabbed": {r["url_key"]: r["saved_as"] for r in rows}}


@router.get("/insights")
async def insights(days: int = Query(default=30, le=365), principal=Depends(require_auth)):
    by_day = await db.fetch(
        """
        SELECT date_trunc('day', ts)::date AS day,
               count(*) AS files, coalesce(sum(bytes),0) AS bytes
        FROM zipper.history
        WHERE ts > now() - ($1 || ' days')::interval AND accepted
        GROUP BY 1 ORDER BY 1
        """,
        str(days),
    )
    by_domain = await db.fetch(
        """
        SELECT domain, count(*) AS files, coalesce(sum(bytes),0) AS bytes
        FROM zipper.history
        WHERE ts > now() - ($1 || ' days')::interval AND accepted
        GROUP BY 1 ORDER BY bytes DESC LIMIT 20
        """,
        str(days),
    )
    by_kind = await db.fetch(
        """
        SELECT coalesce(kind,'unknown') AS kind,
               count(*) AS files, coalesce(sum(bytes),0) AS bytes
        FROM zipper.history
        WHERE ts > now() - ($1 || ' days')::interval AND accepted
        GROUP BY 1 ORDER BY files DESC
        """,
        str(days),
    )
    return {
        "ok": True,
        "by_day": [db.row_to_dict(r) for r in by_day],
        "by_domain": [db.row_to_dict(r) for r in by_domain],
        "by_kind": [db.row_to_dict(r) for r in by_kind],
    }


# -------------------------------------------------------------- profiles ----

@router.get("/profile/{domain}")
async def get_profile(domain: str, principal=Depends(require_auth)):
    row = await db.fetchrow("SELECT * FROM zipper.site_profile WHERE domain = $1", domain)
    return {"ok": True, "profile": db.row_to_dict(row) if row else None}


@router.patch("/profile/{domain}")
async def patch_profile(domain: str, body: ProfilePatch, principal=Depends(require_auth)):
    """Merge learned facts into a domain's profile, creating it if absent."""
    await db.execute(
        "INSERT INTO zipper.site_profile (domain) VALUES ($1) ON CONFLICT (domain) DO NOTHING",
        domain,
    )

    sets, args = [], []

    def put(col: str, val: Any) -> None:
        args.append(val)
        sets.append(f"{col} = ${len(args)}")

    for col in ("accepted_patterns", "rejected_patterns", "learned_upgrades",
                "best_origin", "title_source", "default_route", "default_scope",
                "needs_scroll", "connection_policy", "confidence",
                "last_full_count", "last_fast_count"):
        val = getattr(body, col)
        if val is not None:
            put(col, val)

    if body.mark_full_scan:
        sets.append("last_full_scan = now()")
        sets.append("scan_count = scan_count + 1")

    if not sets:
        return {"ok": True, "unchanged": True}

    args.append(domain)
    await db.execute(
        f"UPDATE zipper.site_profile SET {', '.join(sets)} WHERE domain = ${len(args)}",
        *args,
    )
    row = await db.fetchrow("SELECT * FROM zipper.site_profile WHERE domain = $1", domain)
    return {"ok": True, "profile": db.row_to_dict(row)}


@router.delete("/profile/{domain}")
async def delete_profile(domain: str, principal=Depends(require_auth)):
    """Reset a domain's learned layer. Costs exactly one full scan."""
    await db.execute("DELETE FROM zipper.site_profile WHERE domain = $1", domain)
    return {"ok": True}


# ---------------------------------------------------------------- quotas ----

@router.get("/quota")
async def get_quota(principal=Depends(require_auth)):
    today = date.today()
    usage = await db.fetch("SELECT * FROM zipper.quota WHERE day = $1", today)
    limits = await db.fetch("SELECT * FROM zipper.quota_limit")
    lim = {r["provider"]: db.row_to_dict(r) for r in limits}
    out = {}
    for r in usage:
        p = r["provider"]
        out[p] = {"grabs": r["grabs"], "bytes": r["bytes"], "limit": lim.get(p)}
    for p, l in lim.items():
        out.setdefault(p, {"grabs": 0, "bytes": 0, "limit": l})
    return {"ok": True, "day": today.isoformat(), "providers": out}


@router.post("/quota/check")
async def check_quota(body: QuotaSpend, principal=Depends(require_auth)):
    """Would this spend exceed the provider's daily limit?

    Checked before dispatch, never after. A refusal names the limit it hit and
    when it resets, because silently queueing past a stingy provider's cap is
    how the account goes rather than the afternoon.
    """
    today = date.today()
    lim = await db.fetchrow(
        "SELECT * FROM zipper.quota_limit WHERE provider = $1", body.provider,
    )
    if not lim or not lim["enabled"]:
        return {"ok": True, "allowed": True, "reason": None}

    cur = await db.fetchrow(
        "SELECT grabs, bytes FROM zipper.quota WHERE provider = $1 AND day = $2",
        body.provider, today,
    )
    grabs = (cur["grabs"] if cur else 0) + body.grabs
    used_bytes = (cur["bytes"] if cur else 0) + body.bytes

    if lim["max_grabs_day"] is not None and grabs > lim["max_grabs_day"]:
        return {
            "ok": True, "allowed": False,
            "reason": f"{body.provider}: {grabs} grabs would exceed the daily "
                      f"limit of {lim['max_grabs_day']}",
            "resets": "00:00 UTC",
        }
    if lim["max_bytes_day"] is not None and used_bytes > lim["max_bytes_day"]:
        gb = round(lim["max_bytes_day"] / 1e9, 1)
        return {
            "ok": True, "allowed": False,
            "reason": f"{body.provider}: {round(used_bytes / 1e9, 1)} GB would "
                      f"exceed the daily limit of {gb} GB",
            "resets": "00:00 UTC",
        }
    return {"ok": True, "allowed": True, "reason": None}


@router.post("/quota/spend")
async def spend_quota(body: QuotaSpend, principal=Depends(require_auth)):
    await db.execute(
        """
        INSERT INTO zipper.quota (provider, day, grabs, bytes)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (provider, day) DO UPDATE SET
            grabs = quota.grabs + EXCLUDED.grabs,
            bytes = quota.bytes + EXCLUDED.bytes
        """,
        body.provider, date.today(), body.grabs, body.bytes,
    )
    return {"ok": True}


@router.get("/health")
async def health(principal=Depends(require_auth)):
    await db.ensure_schema()
    row = await db.fetchrow("SELECT count(*) AS n FROM zipper.jobs")
    return {"ok": True, "jobs": row["n"] if row else 0}
