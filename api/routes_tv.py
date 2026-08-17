"""Metadata gateway for the Vault TV thin client.

Vault TV used to call api.themoviedb.org and api.kinocheck.com straight from its
WebView, with the TMDB v4 bearer compiled into the JavaScript bundle. That broke
two things at once:

  * the client's own guardrail ("keep secrets out of the client bundle", and
    keep provider lookup server-side) — the token shipped inside index-*.js and
    worked from anywhere it was extracted from;
  * reachability — the TV reaches Comet over Tailscale, but every metadata call
    needed public DNS and a public route from the device itself.

Routing both upstreams through here fixes both: the token stays on the server,
and the TV only ever talks to one host it already reaches.

Deliberately an allow-listed proxy, not a general one. `{path:path}` would
otherwise let any authenticated caller use the gateway — and its TMDB
credentials — as an open relay to arbitrary URLs.
"""

import logging
import os
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.auth import require_auth

router = APIRouter(prefix="/tv", tags=["vault-tv"])
logger = logging.getLogger("vaultwares.api")

TMDB_BASE = "https://api.themoviedb.org/3"
KINOCHECK_BASE = "https://api.kinocheck.com"

# The token is looked up rather than pinned to one path: this module runs both on
# the Windows workstation and on the Linux VPS, and a single hardcoded path is
# simply absent on the other. Env var first, so deployment never depends on a
# file landing in the right place.
TMDB_TOKEN_PATHS = (
    Path("/opt/vaultwares-api/.access/tmdb_bearer.txt"),
    Path("/etc/vaultwares/tmdb_bearer.txt"),
    Path("C:/Users/Administrator/Desktop/Github Repos/.access/tmdb_bearer.txt"),
)

UPSTREAM_TIMEOUT_SECONDS = 20.0

# Exactly the endpoints vault-tv's TmdbClient calls, and nothing else. Kept as
# full-match patterns so a new client call fails loudly here rather than silently
# widening what the gateway will relay.
_TMDB_ALLOWED = (
    re.compile(r"^trending/(movie|tv)/week$"),
    re.compile(r"^(movie|tv)/popular$"),
    re.compile(r"^movie/top_rated$"),
    re.compile(r"^(movie|tv)/\d+$"),
    re.compile(r"^(movie|tv)/\d+/external_ids$"),
    re.compile(r"^tv/\d+/season/\d+$"),
    re.compile(r"^search/(movie|tv)$"),
    re.compile(r"^discover/(movie|tv)$"),
    re.compile(r"^genre/(movie|tv)/list$"),
)

# Query keys worth forwarding. Anything else is dropped rather than passed on, so
# a caller cannot smuggle an api_key/session_id of its own into our request.
_TMDB_QUERY_ALLOWED = {
    "language",
    "page",
    "query",
    "append_to_response",
    "with_genres",
    "with_original_language",
    "sort_by",
    "year",
    "primary_release_year",
    "vote_count.gte",
    "include_adult",
}

_tmdb_token_cache: str | None = None


def _tmdb_token() -> str:
    global _tmdb_token_cache
    if _tmdb_token_cache:
        return _tmdb_token_cache
    token = os.getenv("TMDB_BEARER_TOKEN", "").strip()
    if not token:
        for candidate in TMDB_TOKEN_PATHS:
            try:
                if candidate.exists():
                    token = candidate.read_text(encoding="utf-8").strip()
                    if token:
                        break
            except OSError:
                continue
    if not token:
        raise HTTPException(
            status_code=503,
            detail="TMDB credentials are not provisioned on this server.",
        )
    _tmdb_token_cache = token
    return token


def _tmdb_allowed(path: str) -> bool:
    return any(pattern.match(path) for pattern in _TMDB_ALLOWED)


@router.get("/tmdb/{path:path}")
async def tmdb_proxy(path: str, request: Request, _auth=Depends(require_auth)):
    """Relay one allow-listed TMDB read, adding the server-held bearer."""
    path = path.strip("/")
    if not _tmdb_allowed(path):
        # 404 rather than 403: the caller asked for something this gateway does
        # not expose, and echoing "forbidden" invites probing for what it does.
        raise HTTPException(status_code=404, detail=f"Unsupported TMDB path: {path}")

    params = {k: v for k, v in request.query_params.items() if k in _TMDB_QUERY_ALLOWED}

    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
            upstream = await client.get(
                f"{TMDB_BASE}/{path}",
                params=params,
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {_tmdb_token()}",
                },
            )
    except httpx.RequestError as exc:
        logger.warning("TMDB proxy failed for %s: %s", path, exc)
        raise HTTPException(status_code=502, detail="TMDB is unreachable from the gateway.")

    if upstream.status_code >= 400:
        # Pass the status through so the client can tell "no such title" from
        # "we are rate limited", but never the upstream body — it can echo the
        # request, and that is where our credentials would surface.
        logger.warning("TMDB %s for %s", upstream.status_code, path)
        raise HTTPException(status_code=upstream.status_code, detail=f"TMDB error {upstream.status_code}")

    return JSONResponse(content=upstream.json())


@router.get("/trailer/{kind}")
async def kinocheck_proxy(kind: str, request: Request, _auth=Depends(require_auth)):
    """Relay a KinoCheck trailer lookup. `kind` is 'movies' or 'shows'."""
    if kind not in ("movies", "shows"):
        raise HTTPException(status_code=404, detail="Unsupported trailer kind")

    tmdb_id = request.query_params.get("tmdb_id", "")
    if not tmdb_id.isdigit():
        raise HTTPException(status_code=400, detail="tmdb_id must be numeric")

    params = {"tmdb_id": tmdb_id, "language": request.query_params.get("language", "en")}

    try:
        async with httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS) as client:
            upstream = await client.get(
                f"{KINOCHECK_BASE}/{kind}",
                params=params,
                headers={"accept": "application/json"},
            )
    except httpx.RequestError as exc:
        logger.warning("KinoCheck proxy failed for %s/%s: %s", kind, tmdb_id, exc)
        raise HTTPException(status_code=502, detail="KinoCheck is unreachable from the gateway.")

    if upstream.status_code == 404:
        # A title with no curated trailer is ordinary, not an error worth
        # surfacing to the TV as a failure.
        return JSONResponse(content={})
    if upstream.status_code >= 400:
        raise HTTPException(status_code=upstream.status_code, detail=f"KinoCheck error {upstream.status_code}")

    return JSONResponse(content=upstream.json())
