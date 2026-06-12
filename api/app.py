import os
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api.config import (
    CORS_ORIGINS, ALLOWED_ORIGINS, DB_URL, BOOTSTRAP_ADMIN_USERNAME,
    BOOTSTRAP_ADMIN_PASSWORD, BOOTSTRAP_ADMIN_IS_DISABLED,
    JOB_QUEUE_MAX_PENDING, JOB_WORKER_CONCURRENCY
)
from api.auth import pwd_context
from db import init_db, close_db, UserAccount
from api.middleware import gate_requests_middleware, correlation_id_middleware
from api import database

# Load routers
from api.routes_auth import router as auth_router
from api.routes_webauthn import router as webauthn_router
from api.routes_workflows import router as workflows_router
from api.routes_flows import router as flows_router
from api.routes_jobs import router as jobs_router
from api.routes_uploads import router as uploads_router
from api.routes_promking import router as promking_router
from api.routes_proxy import router as proxy_router
from api.routes_media import router as media_router

from api.routes_media import ZIPPER_DEST_DIR

import logging
logger = logging.getLogger("vaultwares.api")

app = FastAPI(
    title="VaultWares API",
    description="Central API for VaultWares auth, DB-backed telemetry, monitor reads, logging, workflows, and media services.",
    version="0.2.0",
)

# Correlation ID and Security/Rate-Limit middlewares
app.middleware("http")(correlation_id_middleware)
app.middleware("http")(gate_requests_middleware)

# CORS
_cors_allow_origins = sorted(set(CORS_ORIGINS) | ALLOWED_ORIGINS) if (CORS_ORIGINS or ALLOWED_ORIGINS) else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files
_faceswap_static_dir = os.environ.get("FACESWAP_STATIC_DIR")
if _faceswap_static_dir and os.path.isdir(_faceswap_static_dir):
    app.mount("/faceswap", StaticFiles(directory=_faceswap_static_dir, html=True), name="faceswap")

os.makedirs(ZIPPER_DEST_DIR, exist_ok=True)
app.mount("/downloaded", StaticFiles(directory=ZIPPER_DEST_DIR), name="downloaded")

# Include Routers
app.include_router(auth_router)
app.include_router(webauthn_router)
app.include_router(workflows_router)
app.include_router(flows_router)
app.include_router(jobs_router)
app.include_router(uploads_router)
app.include_router(proxy_router)
app.include_router(media_router)

# Resiliency router imports
_PROMKING_LOADED = False
try:
    from app.routers.promking import router as promking_module_router
    app.include_router(promking_module_router)
    _PROMKING_LOADED = True
except Exception as err:
    logger.warning("Prom-King router not loaded: %s", err)

_MONITOR_LOADED = False
try:
    from app.routers.monitor import router as monitor_router
    app.include_router(monitor_router)
    _MONITOR_LOADED = True
except Exception as err:
    logger.warning("Monitor router not loaded: %s", err)

_TELEMETRY_LOADED = False
try:
    from app.routers.telemetry import router as telemetry_router
    app.include_router(telemetry_router)
    _TELEMETRY_LOADED = True
except Exception as err:
    logger.warning("Telemetry router not loaded: %s", err)

@app.on_event("startup")
async def startup_event():
    try:
        await init_db(DB_URL)
        database._tortoise_initialized = True
        logger.info("Tortoise ORM initialized successfully.")

        if BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD:
            existing = await UserAccount.get_or_none(username=BOOTSTRAP_ADMIN_USERNAME)
            if not existing:
                await UserAccount.create(
                    username=BOOTSTRAP_ADMIN_USERNAME,
                    password_hash=pwd_context.hash(BOOTSTRAP_ADMIN_PASSWORD),
                    is_admin=True,
                    is_disabled=BOOTSTRAP_ADMIN_IS_DISABLED,
                )
                logger.info("Bootstrapped initial admin user.")
    except Exception as e:
        logger.error(f"Failed to initialize Tortoise ORM: {e}")
        database._tortoise_initialized = False

    if _PROMKING_LOADED:
        try:
            from app.routers.promking.cron import start_scheduler as _pk_start
            await _pk_start()
        except Exception as _pk_err:
            logger.warning("Prom-King APScheduler not started: %s", _pk_err)

    from api.routes_jobs import _job_worker, _list_jobs, _JobQueueItem
    from api.config import JOBS_DIR
    os.makedirs(JOBS_DIR, exist_ok=True)
    
    if not hasattr(app.state, "workflow_job_lock"):
        app.state.workflow_job_lock = asyncio.Lock()
    if not hasattr(app.state, "job_queue"):
        app.state.job_queue = asyncio.Queue(maxsize=JOB_QUEUE_MAX_PENDING)
        app.state.job_workers = [
            asyncio.create_task(_job_worker(app, index + 1))
            for index in range(JOB_WORKER_CONCURRENCY)
        ]
        try:
            durable = _list_jobs(limit=JOB_QUEUE_MAX_PENDING)
            queued = [j for j in durable if j.get("status") == "queued"]
            queued.sort(key=lambda j: float(j.get("created_at") or 0))
            for job in queued:
                try: app.state.job_queue.put_nowait(_JobQueueItem(job_id=str(job.get("id"))))
                except asyncio.QueueFull: break
        except Exception: pass

@app.on_event("shutdown")
async def shutdown_event():
    try:
        if hasattr(app.state, "job_workers"):
            for task in list(app.state.job_workers):
                task.cancel()
        await close_db()
        logger.info("Tortoise ORM connections closed.")
    except Exception as e:
        logger.error(f"Error closing Tortoise ORM connections: {e}")

    if _PROMKING_LOADED:
        try:
            from app.routers.promking.cron import stop_scheduler as _pk_stop
            from app.routers.promking.db import close_pool as _pk_close
            await _pk_stop()
            await _pk_close()
        except Exception as _pk_err:
            logger.warning("Prom-King shutdown warning: %s", _pk_err)

    if _TELEMETRY_LOADED:
        try:
            from app.routers.telemetry.db import close_pool as _telemetry_close
            await _telemetry_close()
        except Exception as _telemetry_err:
            logger.warning("Telemetry shutdown warning: %s", _telemetry_err)
