"""Monetised short links behind the tube homepages' "Feeling Lucky" /
"Pick For Me" pills.

Each homepage load asks `/short-links/lucky?site=<site>` for one link per
provider (exe.io → "Feeling Lucky", cuty.io → "Pick For Me"). The two links
always point at two different videos. A link is either:

  * reused — a random pre-existing short link for that (site, provider), or
  * new    — a random not-yet-shortened video on that site, shortened through
             the provider's API and persisted to `short_links`.

The reuse odds grow with the per-(site, provider) pool size so the catalog
gets coverage first and the provider quota is spared later
(see `reuse_probability`). Sites are never mixed: every query is scoped to a
single site.

Impressions (`serve`) and clicks (`click`) land in `short_link_events` and on
the counters of `short_links`, which the admin "Short Links" tab reads through
`/short-links/stats`.

Provider tokens come from the environment and never leave the server:
  EXEIO_API_TOKEN   exe.io "api" key
  CUTY_API_TOKEN    cuty.io "token"
A provider whose token is missing still serves reused links, and otherwise
falls back to the plain video URL (not persisted).
"""
from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import unicodedata
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .db import get_pool

log = logging.getLogger(__name__)

router = APIRouter(prefix="/short-links", tags=["promking:short-links"])

Provider = Literal["exeio", "cuty"]
TubeSite = Literal["fxv", "oneporn", "sexyprn"]

PROVIDERS: tuple[Provider, ...] = ("exeio", "cuty")

SITE_DOMAINS: dict[str, str] = {
    "fxv": "fullxxx.video",
    "oneporn": "1pornhub.vip",
    "sexyprn": "sexyprn.lol",
}
SITE_ALIAS_PREFIX: dict[str, str] = {
    "fxv": "FXV",
    "oneporn": "1PH",
    "sexyprn": "SPN",
}

# Conservative cap: AdLinkFly-style shorteners (exe.io, cuty.io) reject long
# aliases. Prefix + "_" + PascalCase title is truncated to fit.
ALIAS_MAX_LEN = 30
PROVIDER_TIMEOUT_S = 5.0
# Cap concurrent provider calls per process. While the pool is small every
# page load wants a fresh link; under a burst the overflow is served an
# existing link (or the plain URL) instead of queueing on the provider.
_PROVIDER_SLOTS = asyncio.Semaphore(4)

# (pool size threshold, reuse probability) — highest threshold first.
REUSE_TIERS: tuple[tuple[int, float], ...] = ((500, 0.75), (200, 0.50), (100, 0.25))


def reuse_probability(pool_size: int) -> float:
    for threshold, probability in REUSE_TIERS:
        if pool_size >= threshold:
            return probability
    return 0.0


def video_url(site: str, slug: str) -> str:
    return f"https://{SITE_DOMAINS[site]}/videos/{slug}"


_NON_ALNUM = re.compile(r"[^A-Za-z0-9]+")


def make_alias(site: str, title: str, video_id: int | None = None, provider: str = "exeio") -> str:
    """`FXV_HotMilfGetsCaught` — ASCII PascalCase of the title, capped.

    cuty.io only accepts letters and digits, so its aliases drop the
    separator (`FXVHotMilfGetsCaught`). `video_id` is spliced in
    (`FXV_1234_HotMilf…`) for the retry after the provider rejected the
    plain alias as taken.
    """
    sep = "" if provider == "cuty" else "_"
    ascii_title = unicodedata.normalize("NFKD", title or "").encode("ascii", "ignore").decode("ascii")
    words = [w for w in _NON_ALNUM.split(ascii_title) if w]
    name = "".join(w[:1].upper() + w[1:].lower() for w in words) or "Video"
    prefix = SITE_ALIAS_PREFIX[site]
    head = f"{prefix}{sep}{video_id}{sep}" if video_id is not None else f"{prefix}{sep}"
    return (head + name)[:ALIAS_MAX_LEN]


# ── Provider calls ──────────────────────────────────────────────────────────

class ShortenError(Exception):
    def __init__(self, message: str, *, rejected: bool = False):
        super().__init__(message)
        # True when the provider answered with an error (e.g. alias taken),
        # False for transport failures / missing token — not worth a retry.
        self.rejected = rejected


def _provider_token(provider: Provider) -> str | None:
    env = "EXEIO_API_TOKEN" if provider == "exeio" else "CUTY_API_TOKEN"
    return (os.environ.get(env) or "").strip() or None


def _extract_short_url(res: httpx.Response) -> str:
    """Both providers answer JSON on success, but their key names differ
    (`shortenedUrl` for AdLinkFly/exe.io, `short_url`/`url` variants for
    cuty). Accept any of them, or a bare URL body."""
    text = res.text.strip()
    try:
        data = res.json()
    except ValueError:
        data = None
    if isinstance(data, dict):
        status = str(data.get("status", "")).lower()
        if status in ("error", "fail", "failed") or data.get("error") or data.get("success") is False:
            raise ShortenError(str(data.get("message") or data.get("error") or data), rejected=True)
        candidates = [data, data.get("data") if isinstance(data.get("data"), dict) else {}]
        for bag in candidates:
            for key in ("shortenedUrl", "short_url", "shortUrl", "shorturl", "url", "link"):
                value = bag.get(key)
                if isinstance(value, str) and value.startswith("http"):
                    return value
        raise ShortenError(f"no short url in response: {text[:200]}", rejected=True)
    if text.startswith("http"):
        return text
    raise ShortenError(f"unexpected response ({res.status_code}): {text[:200]}", rejected=True)


async def shorten(client: httpx.AsyncClient, provider: Provider, url: str, alias: str | None) -> str:
    token = _provider_token(provider)
    if not token:
        raise ShortenError(f"{provider} token not configured")
    if provider == "exeio":
        endpoint = "https://exe.io/api"
        params = {"api": token, "url": url}
    else:
        endpoint = "https://api.cuty.io/quick"
        params = {"token": token, "url": url}
    if alias:
        params["alias"] = alias
    try:
        res = await client.get(endpoint, params=params, timeout=PROVIDER_TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise ShortenError(f"{provider} request failed: {exc.__class__.__name__}") from exc
    return _extract_short_url(res)


# ── Schema ──────────────────────────────────────────────────────────────────
# Mirrors shared-tube/shared/drizzle/0011_short_links.sql. Applied lazily and
# idempotently so a deploy of this router does not depend on a separate
# migration step against prod.

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS short_links (
    id serial PRIMARY KEY,
    site site NOT NULL,
    provider text NOT NULL,
    video_id integer NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    target_url text NOT NULL,
    alias text,
    short_url text NOT NULL,
    served_count integer NOT NULL DEFAULT 0,
    click_count integer NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    last_served_at timestamptz,
    last_clicked_at timestamptz
);
CREATE UNIQUE INDEX IF NOT EXISTS short_links_site_provider_video_uniq
    ON short_links (site, provider, video_id);
CREATE INDEX IF NOT EXISTS short_links_site_provider_idx ON short_links (site, provider);
CREATE TABLE IF NOT EXISTS short_link_events (
    id bigserial PRIMARY KEY,
    link_id integer NOT NULL REFERENCES short_links(id) ON DELETE CASCADE,
    kind text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS short_link_events_link_idx ON short_link_events (link_id);
CREATE INDEX IF NOT EXISTS short_link_events_created_at_idx ON short_link_events (created_at);
"""

_schema_ready = False
# Concurrent CREATE ... IF NOT EXISTS can still collide in pg_type; serialise.
_schema_lock = asyncio.Lock()


async def _ensure_schema(conn) -> None:
    global _schema_ready
    if _schema_ready:
        return
    async with _schema_lock:
        if not _schema_ready:
            await conn.execute(_SCHEMA_SQL)
            _schema_ready = True


# ── Picking ─────────────────────────────────────────────────────────────────

async def _pick_existing(conn, site: str, provider: str, exclude: list[int]):
    return await conn.fetchrow(
        """
        SELECT sl.id, sl.short_url, sl.video_id, v.slug, v.title
        FROM short_links sl
        JOIN videos v ON v.id = sl.video_id
        WHERE sl.site = $1 AND sl.provider = $2
          AND v.disabled_at IS NULL
          AND NOT (sl.video_id = ANY($3::int[]))
        ORDER BY random()
        LIMIT 1
        """,
        site, provider, exclude,
    )


async def _pick_fresh_video(conn, site: str, provider: str, exclude: list[int]):
    """Random enabled, non-OnlyFans video on `site` with no `provider` link
    yet. Seeks from a random id pivot (index-friendly) instead of
    ORDER BY random() over the whole catalog, wrapping to the start once."""
    bounds = await conn.fetchrow(
        "SELECT min(video_id) AS lo, max(video_id) AS hi FROM video_sites WHERE site = $1",
        site,
    )
    if not bounds or bounds["lo"] is None:
        return None
    pivot = random.randint(bounds["lo"], bounds["hi"])
    for start in (pivot, bounds["lo"]):
        row = await conn.fetchrow(
            """
            SELECT v.id, v.slug, v.title
            FROM videos v
            JOIN video_sites vs ON vs.video_id = v.id AND vs.site = $1
            WHERE v.id >= $2
              AND v.disabled_at IS NULL
              AND v.is_onlyfans = false
              AND NOT (v.id = ANY($3::int[]))
              AND NOT EXISTS (
                  SELECT 1 FROM short_links sl
                  WHERE sl.site = $1 AND sl.provider = $4 AND sl.video_id = v.id
              )
            ORDER BY v.id
            LIMIT 1
            """,
            site, start, exclude, provider,
        )
        if row:
            return row
    return None


async def _create_link(pool, client: httpx.AsyncClient, site: str, provider: Provider, video) -> dict | None:
    """Shorten `video` through `provider` and persist it. No DB connection is
    held while the provider is called."""
    if _PROVIDER_SLOTS.locked() or not _provider_token(provider):
        return None
    target = video_url(site, video["slug"])
    # Plain alias → id-qualified alias (title collision after truncation) →
    # no alias (provider-side alias rule we don't know about). Transport
    # failures stop the chain immediately.
    attempts = [
        make_alias(site, video["title"], provider=provider),
        make_alias(site, video["title"], video["id"], provider=provider),
        None,
    ]
    short_url: str | None = None
    alias: str | None = None
    errors: list[str] = []
    async with _PROVIDER_SLOTS:
        for alias in attempts:
            try:
                short_url = await shorten(client, provider, target, alias)
                break
            except ShortenError as exc:
                errors.append(str(exc))
                if not exc.rejected:
                    break
    if short_url is None:
        log.warning("short-links: %s failed for video %s: %s", provider, video["id"], " / ".join(errors))
        return None
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO short_links (site, provider, video_id, target_url, alias, short_url)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (site, provider, video_id) DO NOTHING
            RETURNING id, short_url
            """,
            site, provider, video["id"], target, alias, short_url,
        )
        if row is None:
            # A concurrent page load shortened the same video first; use its row.
            row = await conn.fetchrow(
                "SELECT id, short_url FROM short_links WHERE site = $1 AND provider = $2 AND video_id = $3",
                site, provider, video["id"],
            )
    return {"id": row["id"], "url": row["short_url"], "video_id": video["id"],
            "slug": video["slug"], "title": video["title"], "reused": False}


async def _record_serve(conn, link_id: int) -> None:
    await conn.execute(
        "UPDATE short_links SET served_count = served_count + 1, last_served_at = now() WHERE id = $1",
        link_id,
    )
    await conn.execute(
        "INSERT INTO short_link_events (link_id, kind) VALUES ($1, 'serve')",
        link_id,
    )


class LuckyLink(BaseModel):
    provider: Provider
    # null when the link is the un-shortened fallback (nothing persisted).
    id: int | None
    url: str
    video_slug: str
    video_title: str
    reused: bool
    shortened: bool


class LuckyResponse(BaseModel):
    site: TubeSite
    links: dict[str, LuckyLink | None]


def _existing(row) -> dict:
    return {"id": row["id"], "url": row["short_url"], "video_id": row["video_id"],
            "slug": row["slug"], "title": row["title"], "reused": True}


@router.get("/lucky", response_model=LuckyResponse)
async def lucky(site: TubeSite = Query(...)) -> LuckyResponse:
    pool = await get_pool()
    links: dict[str, LuckyLink | None] = {}
    used_videos: list[int] = []
    async with httpx.AsyncClient() as client:
        for provider in PROVIDERS:
            picked: dict | None = None
            fresh_video = None
            async with pool.acquire() as conn:
                await _ensure_schema(conn)
                pool_size = await conn.fetchval(
                    "SELECT COUNT(*) FROM short_links WHERE site = $1 AND provider = $2",
                    site, provider,
                )
                if random.random() < reuse_probability(pool_size or 0):
                    row = await _pick_existing(conn, site, provider, used_videos)
                    if row:
                        picked = _existing(row)
                if picked is None:
                    fresh_video = await _pick_fresh_video(conn, site, provider, used_videos)

            if picked is None and fresh_video is not None:
                picked = await _create_link(pool, client, site, provider, fresh_video)

            async with pool.acquire() as conn:
                if picked is None:
                    # Provider down / no token / busy / every video already
                    # shortened: an existing link beats a bare URL.
                    row = await _pick_existing(conn, site, provider, used_videos)
                    if row:
                        picked = _existing(row)
                if picked is not None:
                    await _record_serve(conn, picked["id"])

            if picked is not None:
                used_videos.append(picked["video_id"])
                links[provider] = LuckyLink(
                    provider=provider, id=picked["id"], url=picked["url"],
                    video_slug=picked["slug"], video_title=picked["title"],
                    reused=picked["reused"], shortened=True,
                )
            elif fresh_video is not None:
                used_videos.append(fresh_video["id"])
                links[provider] = LuckyLink(
                    provider=provider, id=None, url=video_url(site, fresh_video["slug"]),
                    video_slug=fresh_video["slug"], video_title=fresh_video["title"],
                    reused=False, shortened=False,
                )
            else:
                links[provider] = None
    return LuckyResponse(site=site, links=links)


@router.post("/{link_id}/click")
async def record_click(link_id: int) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _ensure_schema(conn)
        updated = await conn.execute(
            "UPDATE short_links SET click_count = click_count + 1, last_clicked_at = now() WHERE id = $1",
            link_id,
        )
        if updated.endswith(" 0"):
            raise HTTPException(status_code=404, detail=f"short link {link_id} not found")
        await conn.execute(
            "INSERT INTO short_link_events (link_id, kind) VALUES ($1, 'click')",
            link_id,
        )
    return {"ok": True}


@router.get("/stats")
async def short_link_stats(
    site: TubeSite = Query(...),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(50, ge=1, le=500),
) -> dict:
    """Admin analytics: per-provider totals, a daily serve/click series over
    `days`, and the top links by clicks (then impressions)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await _ensure_schema(conn)
        totals = await conn.fetch(
            """
            SELECT provider,
                   COUNT(*)                         AS links,
                   COALESCE(SUM(served_count), 0)   AS served,
                   COALESCE(SUM(click_count), 0)    AS clicks,
                   COUNT(*) FILTER (WHERE created_at >= now() - interval '24 hours') AS created_24h
            FROM short_links
            WHERE site = $1
            GROUP BY provider
            """,
            site,
        )
        daily = await conn.fetch(
            """
            SELECT date_trunc('day', e.created_at)::date AS day, sl.provider,
                   COUNT(*) FILTER (WHERE e.kind = 'serve') AS served,
                   COUNT(*) FILTER (WHERE e.kind = 'click') AS clicks
            FROM short_link_events e
            JOIN short_links sl ON sl.id = e.link_id
            WHERE sl.site = $1 AND e.created_at >= now() - make_interval(days => $2)
            GROUP BY 1, 2
            ORDER BY 1
            """,
            site, days,
        )
        top = await conn.fetch(
            """
            SELECT sl.id, sl.provider, sl.short_url, sl.alias, sl.target_url,
                   sl.served_count, sl.click_count, sl.created_at, sl.last_clicked_at,
                   v.slug AS video_slug, v.title AS video_title
            FROM short_links sl
            JOIN videos v ON v.id = sl.video_id
            WHERE sl.site = $1
            ORDER BY sl.click_count DESC, sl.served_count DESC, sl.created_at DESC
            LIMIT $2
            """,
            site, limit,
        )

    by_provider = {r["provider"]: r for r in totals}
    providers = []
    for provider in PROVIDERS:
        r = by_provider.get(provider)
        links = int(r["links"]) if r else 0
        served = int(r["served"]) if r else 0
        clicks = int(r["clicks"]) if r else 0
        providers.append({
            "provider": provider,
            "links": links,
            "served": served,
            "clicks": clicks,
            "ctr": (clicks / served) if served else 0.0,
            "created_24h": int(r["created_24h"]) if r else 0,
            "reuse_probability": reuse_probability(links),
        })
    return {
        "site": site,
        "days": days,
        "reuse_tiers": [{"threshold": t, "probability": p} for t, p in sorted(REUSE_TIERS)],
        "providers": providers,
        "daily": [
            {"day": r["day"].isoformat(), "provider": r["provider"],
             "served": int(r["served"]), "clicks": int(r["clicks"])}
            for r in daily
        ],
        "top_links": [
            {
                "id": r["id"], "provider": r["provider"], "short_url": r["short_url"],
                "alias": r["alias"], "target_url": r["target_url"],
                "served": r["served_count"], "clicks": r["click_count"],
                "created_at": r["created_at"].isoformat(),
                "last_clicked_at": r["last_clicked_at"].isoformat() if r["last_clicked_at"] else None,
                "video_slug": r["video_slug"], "video_title": r["video_title"],
            }
            for r in top
        ],
    }
