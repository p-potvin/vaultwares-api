"""
Prom-King router — mounts /api/promking/* under the FastAPI auth-bridge.

Sub-routes:
  /videos             — read + write video rows in the `promking` Postgres DB
  /taxonomies/{kind}  — actors / studios / categories CRUD
  /fetcher/run        — POST: spawn shared-tube fetcher CLI as a subprocess
  /fetcher/stream/{id}— GET (SSE): relay NDJSON from the running subprocess
  /fetcher/runs       — GET: recent fetch_runs rows
  /settings/{site}    — GET/PUT: per-site JSONB settings
  /stats              — GET: videos per source / fetch-run history / dedupe ratio

Schema is owned by `Prom-King/shared-tube/shared/src/db/schema.ts` (Drizzle).
This router treats the DB as a query target, not a model authority.

See:
  vaultwares-docs/docs-content/adr/0001-shared-tube-rebuild.mdx
  Prom-King/shared-tube/docs/router-integration.md
"""
from fastapi import APIRouter

from .videos import router as videos_router
from .taxonomies import router as taxonomies_router
from .fetcher import router as fetcher_router
from .settings_routes import router as settings_router
from .stats import router as stats_router

router = APIRouter(prefix="/api/promking", tags=["promking"])
router.include_router(videos_router)
router.include_router(taxonomies_router)
router.include_router(fetcher_router)
router.include_router(settings_router)
router.include_router(stats_router)

__all__ = ["router"]
