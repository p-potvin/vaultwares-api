import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
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
from api.routes_llm import router as llm_router
from api.routes_linksharing import router as linksharing_router
from api.routes_projects import router as projects_router
from api.routes_vault import router as vault_router

from api.routes_media import ZIPPER_DEST_DIR

import logging
logger = logging.getLogger("vaultwares.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    from api.config import (
        JOB_QUEUE_MAX_PENDING, JOB_WORKER_CONCURRENCY
    )
    from api.auth import pwd_context
    from db import init_db, close_db, UserAccount
    from api import database

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

    yield

    from db import close_db
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

app = FastAPI(
    title="VaultWares API",
    description="Central API for VaultWares auth, DB-backed telemetry, monitor reads, logging, workflows, and media services.",
    version="0.2.16",
    lifespan=lifespan,
    docs_url=None,  # served below via a self-hosted Swagger UI (default /docs pulls assets from a CDN, which our CSP blocks)
)

# Correlation ID and Security/Rate-Limit middlewares
app.middleware("http")(correlation_id_middleware)
app.middleware("http")(gate_requests_middleware)

# CORS
_extra_dev_origins = {
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:8080", "http://127.0.0.1:8080"
}
_cors_allow_origins = sorted(set(CORS_ORIGINS) | ALLOWED_ORIGINS | _extra_dev_origins) if (CORS_ORIGINS or ALLOWED_ORIGINS) else list(_extra_dev_origins)
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

# Self-hosted Swagger UI assets (served from "self" so our CSP allows them, unlike the CDN default).
# Vendored in-repo (rather than via the swagger-ui-bundle PyPI package, which is stuck on
# swagger-ui 4.15.5 and can't render OpenAPI 3.1 schemas, the version FastAPI/Pydantic v2 emit).
_SWAGGER_UI_STATIC_DIR = Path(__file__).resolve().parent / "static" / "swagger-ui"
app.mount("/static/swagger-ui", StaticFiles(directory=str(_SWAGGER_UI_STATIC_DIR)), name="swagger-ui-static")

_SWAGGER_UI_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<link rel="stylesheet" type="text/css" href="/static/swagger-ui/swagger-ui.css">
<link rel="icon" type="image/png" href="/static/swagger-ui/favicon-32x32.png">
</head>
<body>
<div id="swagger-ui"></div>
<script src="/static/swagger-ui/swagger-ui-bundle.js"></script>
<script src="/static/swagger-ui/swagger-ui-standalone-preset.js"></script>
<script src="/docs/swagger-ui-init.js"></script>
</body>
</html>
"""


@app.get("/docs", include_in_schema=False)
async def swagger_ui_html():
    return HTMLResponse(_SWAGGER_UI_HTML.format(title=f"{app.title} - Swagger UI"))


@app.get("/docs/swagger-ui-init.js", include_in_schema=False)
async def swagger_ui_init_js():
    # Kept as an external, same-origin script rather than inlined in the HTML above:
    # our CSP has no 'unsafe-inline' for script-src, so an inline <script> (which is
    # what fastapi.openapi.docs.get_swagger_ui_html renders) gets silently blocked
    # by the browser and the UI never initializes even though its assets load fine.
    js = (
        "window.onload = function() {\n"
        "  window.ui = SwaggerUIBundle({\n"
        f"    url: {app.openapi_url!r},\n"
        "    dom_id: '#swagger-ui',\n"
        "    deepLinking: true,\n"
        "    presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],\n"
        "    plugins: [SwaggerUIBundle.plugins.DownloadUrl],\n"
        "    layout: 'StandaloneLayout',\n"
        "  });\n"
        "};\n"
    )
    return Response(content=js, media_type="application/javascript")

# Include Routers
app.include_router(auth_router)
app.include_router(webauthn_router)
app.include_router(workflows_router)
app.include_router(flows_router)
app.include_router(jobs_router)
app.include_router(uploads_router)
app.include_router(proxy_router)
app.include_router(media_router)
app.include_router(llm_router)
app.include_router(linksharing_router)
app.include_router(projects_router)
app.include_router(vault_router)

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
