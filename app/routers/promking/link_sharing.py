"""DB-backed Linkvertise automation for Prom-King link_sharing rows."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.zipper.linkvertise import build_linkvertise_pair
from .db import get_pool

router = APIRouter(prefix="/link-sharing", tags=["promking:link-sharing"])

class LinkItem(BaseModel):
    id: str
    slug: str
    title: str
    sources: list[str]
    created_at: str

class LinkListResponse(BaseModel):
    items: list[LinkItem]
    total_count: int
    limit: int
    offset: int

@router.get("/links", response_model=LinkListResponse)
async def list_links(limit: int = 50, offset: int = 0) -> LinkListResponse:
    """Fetch paginated link-sharing rows with resolved sources."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            total = await conn.fetchval("SELECT COUNT(*) FROM link_sharing")
            rows = await conn.fetch(
                """
                SELECT id, slug, title, created_at,
                       fileboom_url, redgifs_url, google_drive_url,
                       linkvertise_url_fxv, linkvertise_url_pkt
                FROM link_sharing
                ORDER BY created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Database error: {exc}") from exc

        items = []
        for row in rows:
            sources = []
            if row.get("fileboom_url"): sources.append("fileboom")
            if row.get("redgifs_url"): sources.append("redgifs")
            if row.get("google_drive_url"): sources.append("google_drive")
            if row.get("linkvertise_url_fxv") or row.get("linkvertise_url_pkt"): sources.append("linkvertise")
            
            items.append(
                LinkItem(
                    id=row["id"],
                    slug=row["slug"],
                    title=row["title"],
                    sources=sources,
                    created_at=row["created_at"].isoformat() if row.get("created_at") else "",
                )
            )

        return LinkListResponse(
            items=items,
            total_count=total or 0,
            limit=limit,
            offset=offset,
        )

class LinkvertiseSyncRequest(BaseModel):
    dry_run: bool = True
    refresh: bool = False
    limit: int = Field(default=100, ge=1, le=1000)
    target_mode: Literal["fileboom", "prelander"] = "fileboom"


class LinkvertiseSyncCandidate(BaseModel):
    id: str
    slug: str
    title: str
    fxv_missing: bool
    pkt_missing: bool
    linkvertise_url_fxv: str
    linkvertise_url_pkt: str


class LinkvertiseSyncResponse(BaseModel):
    dry_run: bool
    target_mode: Literal["fileboom", "prelander"]
    scanned: int
    updated: int
    candidates: list[LinkvertiseSyncCandidate]


@router.post("/linkvertise/sync", response_model=LinkvertiseSyncResponse)
async def sync_linkvertise_urls(req: LinkvertiseSyncRequest) -> LinkvertiseSyncResponse:
    """Generate missing Linkvertise URLs from link_sharing.fileboom_url.

    This does not call Linkvertise or Fileboom. It only fills deterministic
    Linkvertise URLs for DB rows that already have a Fileboom URL.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(
                """
                SELECT id, title, slug, file_path, fileboom_url,
                       linkvertise_url_fxv, linkvertise_url_pkt
                FROM link_sharing
                WHERE NULLIF(fileboom_url, '') IS NOT NULL
                  AND (
                    $1::boolean
                    OR NULLIF(linkvertise_url_fxv, '') IS NULL
                    OR NULLIF(linkvertise_url_pkt, '') IS NULL
                  )
                ORDER BY created_at ASC
                LIMIT $2
                """,
                req.refresh,
                req.limit,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"link_sharing unavailable: {exc}") from exc

        candidates: list[LinkvertiseSyncCandidate] = []
        updates: list[tuple[str, str, str]] = []
        for row in rows:
            try:
                fxv_url, pkt_url = build_linkvertise_pair(
                    fileboom_url=row["fileboom_url"],
                    slug=row["slug"],
                    file_path=row["file_path"],
                    title=row["title"],
                    target_mode=req.target_mode,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=400,
                    detail=f"invalid fileboom_url for row {row['id']}: {exc}",
                ) from exc

            fxv_missing = not row["linkvertise_url_fxv"]
            pkt_missing = not row["linkvertise_url_pkt"]
            candidates.append(
                LinkvertiseSyncCandidate(
                    id=row["id"],
                    slug=row["slug"],
                    title=row["title"],
                    fxv_missing=fxv_missing,
                    pkt_missing=pkt_missing,
                    linkvertise_url_fxv=fxv_url,
                    linkvertise_url_pkt=pkt_url,
                )
            )
            if req.refresh or fxv_missing or pkt_missing:
                updates.append((fxv_url, pkt_url, row["id"]))

        if not req.dry_run and updates:
            await conn.executemany(
                """
                UPDATE link_sharing
                SET linkvertise_url_fxv = $1,
                    linkvertise_url_pkt = $2,
                    updated_at = NOW()
                WHERE id = $3
                """,
                updates,
            )

    return LinkvertiseSyncResponse(
        dry_run=req.dry_run,
        target_mode=req.target_mode,
        scanned=len(rows),
        updated=0 if req.dry_run else len(updates),
        candidates=candidates,
    )
