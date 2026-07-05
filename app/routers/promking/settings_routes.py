"""Per-site settings (JSONB)."""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, HTTPException, Path

from .db import get_pool
from ._models import Site, SettingsPayload

router = APIRouter(prefix="/settings", tags=["promking:settings"])


# ── affiliate_settings validator ──────────────────────────────────────────
# Mirrors shared/src/ads/validate.ts. Kept small and pure so it can be
# unit-tested without spinning up FastAPI. Any rule change must land in both
# files.

AFFILIATE_MAX_BYTES = 32 * 1024  # Layout.astro inlines it all in <head> — cap.
_TAG_PAIRS = (("script", "/script"), ("style", "/style"), ("noscript", "/noscript"))
_FORBIDDEN_CLOSERS = ("</head>", "</body>")


def _iter_head_body_snippets(cfg: Dict[str, Any]):
    """Yield (kind, spotIdx, snippetIdx, snippet) for every head/body snippet."""
    spots = cfg.get("spots") or {}
    for kind in ("head_tags", "body_tags"):
        arr = spots.get(kind) or []
        if not isinstance(arr, list):
            continue
        for si, spot in enumerate(arr):
            if not isinstance(spot, dict):
                continue
            snips = spot.get("snippets") or []
            if not isinstance(snips, list):
                continue
            for ni, snip in enumerate(snips):
                if isinstance(snip, dict):
                    yield kind, si, ni, snip


def validate_affiliate_settings(cfg: Any) -> Tuple[List[dict], List[dict]]:
    """
    Returns (errors, warnings). Errors block the save; warnings pass through.
    """
    errors: List[dict] = []
    warnings: List[dict] = []
    if not isinstance(cfg, dict):
        errors.append({"rule": "shape", "message": "affiliate_settings must be an object"})
        return errors, warnings

    try:
        total = len(json.dumps(cfg))
    except Exception:
        total = 0
    if total > AFFILIATE_MAX_BYTES:
        errors.append({
            "rule": "max_size",
            "message": f"affiliate_settings is {total} bytes; limit is {AFFILIATE_MAX_BYTES}.",
        })

    for kind, si, ni, snip in _iter_head_body_snippets(cfg):
        code = snip.get("code") or ""
        is_active = bool(snip.get("isActive"))
        label = snip.get("label") or f"{kind}#{si}.{ni}"
        loc = {"kind": kind, "spotIndex": si, "snippetIndex": ni, "label": label}
        if is_active and not code.strip():
            errors.append({**loc, "rule": "empty_active",
                           "message": f"{label}: active snippet is empty."})
            continue
        if not code:
            continue
        low = code.lower()
        for closer in _FORBIDDEN_CLOSERS:
            if closer in low:
                errors.append({**loc, "rule": "forbidden_closer",
                               "message": f"{label}: contains stray {closer} — would truncate the page."})
        for open_tag, close_tag in _TAG_PAIRS:
            opens = len(re.findall(rf"<{open_tag}\b", low))
            closes = low.count(f"<{close_tag}>")
            if opens != closes:
                errors.append({**loc, "rule": "unbalanced_tags",
                               "message": f"{label}: <{open_tag}> open={opens} close={closes} — must balance."})
        if "document.write" in low:
            warnings.append({**loc, "rule": "document_write",
                             "message": f"{label}: document.write can block rendering; prefer async injection."})
        if 'http-equiv="refresh"' in low or "http-equiv='refresh'" in low:
            warnings.append({**loc, "rule": "meta_refresh",
                             "message": f"{label}: <meta http-equiv=\"refresh\"> can hurt SEO."})
        if re.search(r"(src|href)=[\"']http://", code):
            warnings.append({**loc, "rule": "mixed_content",
                             "message": f"{label}: http:// resource on an https:// page will be blocked."})

    return errors, warnings


@router.get("/{site}", response_model=dict)
async def get_settings(site: Site = Path(...)) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT key, value, updated_at FROM settings WHERE site = $1",
            site,
        )
    out: Dict[str, Any] = {}
    updated_at: Dict[str, str] = {}
    for r in rows:
        out[r["key"]] = r["value"]
        if r["updated_at"]:
            updated_at[r["key"]] = r["updated_at"].isoformat()
    # Expose per-key updated_at under a reserved key so the panel can render
    # a "last saved" chip without a second round trip. Chosen name is prefixed
    # with `_` so callers already iterating settings keys can filter it out.
    out["_updated_at"] = updated_at
    return out


@router.put("/{site}", response_model=dict)
async def put_settings(payload: SettingsPayload, site: Site = Path(...)) -> dict:
    """
    Upsert one or more settings keys atomically. Returns the persisted values
    (server echo, post-validation) and their updated_at so the admin panel
    can prove the round-trip landed and reflect the DB truth on screen.

    `affiliate_settings` is validated server-side against the same rule set
    the client validator uses (shared/src/ads/validate.ts). A blocking error
    returns 422 with the offending rule list; warnings are surfaced in the
    response but never block.
    """
    validation_errors: List[dict] = []
    validation_warnings: List[dict] = []
    if "affiliate_settings" in payload.values:
        errs, warns = validate_affiliate_settings(payload.values["affiliate_settings"])
        validation_errors.extend(errs)
        validation_warnings.extend(warns)
    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail={"errors": validation_errors, "warnings": validation_warnings},
        )

    pool = await get_pool()
    updated: Dict[str, Any] = {}
    updated_at: Dict[str, str] = {}
    async with pool.acquire() as conn, conn.transaction():
        for key, value in payload.values.items():
            row = await conn.fetchrow(
                """
                INSERT INTO settings (site, key, value, updated_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (site, key) DO UPDATE
                  SET value = EXCLUDED.value,
                      updated_at = NOW()
                RETURNING value, updated_at
                """,
                site,
                key,
                value,
            )
            # asyncpg's jsonb codec (see db.py) decodes on read too, so this
            # is already a native dict/list.
            updated[key] = row["value"]
            updated_at[key] = row["updated_at"].isoformat()

    return {
        "ok": True,
        "updated_keys": list(payload.values.keys()),
        "updated": updated,
        "updated_at": updated_at,
        "warnings": validation_warnings,
    }
