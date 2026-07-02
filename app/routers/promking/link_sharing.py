"""DB-backed Linkvertise automation for Prom-King link_sharing rows.

CRUD lives here alongside the Linkvertise sync — one router keeps every
link_sharing operation on a single table together. The admin Links tab
consumes list/create/update/delete; edit is limited to title + source URLs
because the slug is used across the file-host and Linkvertise URL builders
and must stay stable once created.
"""
from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from app.services.zipper.linkvertise import build_linkvertise_pair
from .db import get_pool

router = APIRouter(prefix="/link-sharing", tags=["promking:link-sharing"])


# Every writable URL column on link_sharing. Kept as a constant so both create
# and update can validate/echo the same fields; add new source columns here
# and both endpoints pick them up automatically.
SOURCE_URL_COLUMNS = (
    "fileboom_url",
    "redgifs_url",
    "google_drive_url",
    "linkvertise_url_fxv",
    "linkvertise_url_pkt",
)


def _source_labels(row: dict) -> list[str]:
    """Derive the human-facing sources[] list the admin renders as chips."""
    sources: list[str] = []
    if row.get("fileboom_url"): sources.append("fileboom")
    if row.get("redgifs_url"): sources.append("redgifs")
    if row.get("google_drive_url"): sources.append("google_drive")
    if row.get("linkvertise_url_fxv") or row.get("linkvertise_url_pkt"):
        sources.append("linkvertise")
    return sources


def _primary_source_url(row: dict) -> str | None:
    """Prefer fileboom for the 'open source' link in the admin table."""
    for col in ("fileboom_url", "redgifs_url", "google_drive_url",
                "linkvertise_url_fxv", "linkvertise_url_pkt"):
        v = row.get(col)
        if v: return v
    return None


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    if not value:
        return ""
    normalised = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalised = normalised.lower()
    normalised = _SLUG_RE.sub("-", normalised).strip("-")
    return normalised[:200]


class LinkItem(BaseModel):
    id: str
    slug: str
    title: str
    sources: list[str]
    # The "open source" link the admin table uses for the direct-link column.
    # Populated from whatever source URL is set (fileboom preferred).
    source_url: str | None = None
    # Full per-column URL bag for the edit modal.
    urls: dict[str, str | None] = Field(default_factory=dict)
    created_at: str


class LinkListResponse(BaseModel):
    items: list[LinkItem]
    total_count: int
    limit: int
    offset: int


class LinkCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    # Slug is optional; server generates it from title when omitted.
    slug: str | None = None
    fileboom_url: str | None = None
    redgifs_url: str | None = None
    google_drive_url: str | None = None
    linkvertise_url_fxv: str | None = None
    linkvertise_url_pkt: str | None = None


class LinkUpdateRequest(BaseModel):
    """Editable fields. Slug is intentionally NOT editable — it's a stable
    external identifier used across the file-host, Linkvertise pairs, and
    telemetry rows."""
    title: str | None = Field(None, min_length=1, max_length=500)
    fileboom_url: str | None = None
    redgifs_url: str | None = None
    google_drive_url: str | None = None
    linkvertise_url_fxv: str | None = None
    linkvertise_url_pkt: str | None = None

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
            row_dict = dict(row)
            items.append(
                LinkItem(
                    id=row["id"],
                    slug=row["slug"],
                    title=row["title"],
                    sources=_source_labels(row_dict),
                    source_url=_primary_source_url(row_dict),
                    urls={col: row_dict.get(col) for col in SOURCE_URL_COLUMNS},
                    created_at=row["created_at"].isoformat() if row.get("created_at") else "",
                )
            )

        return LinkListResponse(
            items=items,
            total_count=total or 0,
            limit=limit,
            offset=offset,
        )


@router.post("/links", response_model=LinkItem, status_code=201)
async def create_link(req: LinkCreateRequest) -> LinkItem:
    """Create a link_sharing row. Slug defaults to slugify(title); server
    rejects if the slug already exists (the caller should either pick another
    title or supply an explicit slug)."""
    slug = req.slug.strip() if req.slug and req.slug.strip() else _slugify(req.title)
    if not slug:
        raise HTTPException(status_code=400, detail="slug is empty and cannot be derived from title")
    link_id = uuid.uuid4().hex

    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM link_sharing WHERE slug = $1",
            slug,
        )
        if exists:
            raise HTTPException(status_code=409, detail=f"slug already exists: {slug}")
        try:
            row = await conn.fetchrow(
                """
                INSERT INTO link_sharing (
                    id, slug, title,
                    fileboom_url, redgifs_url, google_drive_url,
                    linkvertise_url_fxv, linkvertise_url_pkt
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id, slug, title, created_at,
                          fileboom_url, redgifs_url, google_drive_url,
                          linkvertise_url_fxv, linkvertise_url_pkt
                """,
                link_id,
                slug,
                req.title.strip(),
                req.fileboom_url or None,
                req.redgifs_url or None,
                req.google_drive_url or None,
                req.linkvertise_url_fxv or None,
                req.linkvertise_url_pkt or None,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Insert failed: {exc}") from exc

    row_dict = dict(row)
    return LinkItem(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        sources=_source_labels(row_dict),
        source_url=_primary_source_url(row_dict),
        urls={col: row_dict.get(col) for col in SOURCE_URL_COLUMNS},
        created_at=row["created_at"].isoformat() if row.get("created_at") else "",
    )


@router.patch("/links/{link_id}", response_model=LinkItem)
async def update_link(link_id: str, req: LinkUpdateRequest) -> LinkItem:
    """Partial update: only non-None fields are applied. Slug is never
    updatable — clients wanting a new slug should delete + recreate."""
    updates: dict[str, object] = {}
    if req.title is not None:
        updates["title"] = req.title.strip()
    for col in SOURCE_URL_COLUMNS:
        val = getattr(req, col, None)
        if val is not None:
            # Empty string → clear the column (NULL); otherwise trim.
            updates[col] = val.strip() or None
    if not updates:
        raise HTTPException(status_code=400, detail="no updatable fields provided")

    assignments = ", ".join(f"{col} = ${i + 1}" for i, col in enumerate(updates.keys()))
    params = list(updates.values())
    params.append(link_id)
    sql = f"""
        UPDATE link_sharing SET {assignments}, updated_at = NOW()
        WHERE id = ${len(params)}
        RETURNING id, slug, title, created_at,
                  fileboom_url, redgifs_url, google_drive_url,
                  linkvertise_url_fxv, linkvertise_url_pkt
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(sql, *params)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Update failed: {exc}") from exc
    if not row:
        raise HTTPException(status_code=404, detail=f"link {link_id} not found")
    row_dict = dict(row)
    return LinkItem(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        sources=_source_labels(row_dict),
        source_url=_primary_source_url(row_dict),
        urls={col: row_dict.get(col) for col in SOURCE_URL_COLUMNS},
        created_at=row["created_at"].isoformat() if row.get("created_at") else "",
    )


@router.delete("/links/{link_id}", status_code=204)
async def delete_link(link_id: str = Path(...)) -> None:
    """Hard delete from link_sharing. Source files on the file-host are NOT
    touched — this only removes the DB row (per the operator's spec)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(
                "DELETE FROM link_sharing WHERE id = $1",
                link_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Delete failed: {exc}") from exc
    # asyncpg returns "DELETE N" — if N==0 the row didn't exist.
    if isinstance(result, str) and result.endswith(" 0"):
        raise HTTPException(status_code=404, detail=f"link {link_id} not found")

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
