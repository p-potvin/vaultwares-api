"""
Rebuild endpoint — triggers a fresh Astro build + service restart for the
shared-tube apps.

Any change that affects prerender output (e.g. new head/body tags injected
via the Marketing settings) needs a fresh build. Push-to-main normally
triggers this via vw-webhookd; this endpoint gives the admin operator a
manual button when they've edited settings and don't want to bump git.

The endpoint runs the same deploy script vw-webhookd would use:
    /var/www/deploy-scripts/deploy-shared-tube.sh [--site=<site>]
    with SHA=<current-HEAD-of-/srv/repos/Prom-King/shared-tube>

Requires the FastAPI process user to have exec permission on the script.
In production that's granted via ops (sudoers/group). If the script isn't
found or isn't executable, the endpoint returns triggered=false with a
descriptive message rather than raising.

Live status is exposed at GET /api/monitor/deploys, which reads the status
JSON the deploy script writes into /var/lib/vw-deploy/status/. This endpoint
pre-writes a "building" marker so the panel sees in-flight state immediately
instead of waiting for the script to finish its first write.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ._models import Site

router = APIRouter(tags=["promking:rebuild"])


DEFAULT_DEPLOY_SCRIPT = "/var/www/deploy-scripts/deploy-shared-tube.sh"
DEFAULT_REPO_PATH = "/srv/repos/Prom-King/shared-tube"
DEFAULT_STATUS_DIR = "/var/lib/vw-deploy/status"


class RebuildRequest(BaseModel):
    # When set, only that site is rebuilt + its systemd unit restarted. Wired
    # through to `deploy-shared-tube.sh --site=<site>`. Omitted → rebuild all
    # three (historical behaviour, kept for the "just push, rebuild everything"
    # case from vw-webhookd).
    site: Optional[Site] = None


class RebuildResponse(BaseModel):
    triggered: bool
    message: str
    sha: Optional[str] = None
    site: Optional[str] = None


def _resolve_head_sha(repo_path: str) -> Optional[str]:
    """Return the current HEAD SHA of the shared-tube checkout, or None."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            return res.stdout.strip() or None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _pre_write_building_marker(sha: str, site: Optional[str]) -> None:
    """
    Merge a phase=building record into shared-tube.json so /monitor/deploys
    shows in-flight state immediately, even before the shell script has taken
    its first breath. Silently no-op if the status dir isn't writable — the
    script will write the same thing seconds later anyway.
    """
    status_dir = Path(os.environ.get("VW_DEPLOY_STATUS_ROOT") or DEFAULT_STATUS_DIR)
    dest = status_dir / "shared-tube.json"
    try:
        status_dir.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if dest.exists():
            try:
                existing = json.loads(dest.read_text(encoding="utf-8"))
            except Exception:
                existing = {}
        started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        existing["last_build"] = {
            **(existing.get("last_build") or {}),
            "phase": "building",
            "sha": sha,
            "site": site,
            "started_at": started_at,
            "finished_at": None,
            "ok": None,
            "exit_code": None,
        }
        existing.setdefault("project", "shared-tube")
        tmp = dest.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        os.replace(tmp, dest)
    except Exception:
        # Non-fatal: /monitor/deploys will fall back to the lock file mtime.
        pass


@router.post("/rebuild", response_model=RebuildResponse)
async def rebuild(req: RebuildRequest) -> RebuildResponse:
    """
    Fire-and-forget: spawn deploy-shared-tube.sh as a detached subprocess and
    return immediately. The admin panel toasts "triggered" and the actual
    build takes ~30-90s depending on the host. Live progress is at
    GET /api/monitor/deploys?project=shared-tube&logs=true (which the panel
    polls); ops can still tail /var/log/vw-deploy/shared-tube.log directly.
    """
    script = os.environ.get("SHARED_TUBE_DEPLOY_SCRIPT", DEFAULT_DEPLOY_SCRIPT)
    repo_path = os.environ.get("PROMKING_SHARED_TUBE_PATH", DEFAULT_REPO_PATH)

    if not Path(script).exists():
        return RebuildResponse(
            triggered=False,
            message=f"Deploy script not found at {script}. Configure SHARED_TUBE_DEPLOY_SCRIPT or install the deploy hooks.",
        )
    if not os.access(script, os.X_OK):
        return RebuildResponse(
            triggered=False,
            message=f"Deploy script {script} is not executable by the API process user.",
        )

    sha = _resolve_head_sha(repo_path)
    if not sha:
        # Fall back to whatever the script's env sniffs. `deploy-shared-tube.sh`
        # requires SHA to be set, so we still need a value — 'HEAD' works after
        # `git checkout -f HEAD` (a no-op).
        sha = "HEAD"

    # Site is Literal[...] (a plain str) — no .value indirection.
    site = req.site if req.site else None
    _pre_write_building_marker(sha=sha, site=site)

    env = os.environ.copy()
    env["SHA"] = sha
    env["VW_AFTER"] = sha

    args = [script]
    if site:
        args.append(f"--site={site}")

    # Detach: parent-agnostic, no PIPE (script logs to /var/log directly).
    # This means we don't wait for or watch stdout — that's by design; the
    # admin panel is fire-and-forget.
    try:
        await asyncio.create_subprocess_exec(
            *args,
            env=env,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            stdin=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as exc:
        return RebuildResponse(
            triggered=False,
            message=f"Failed to spawn deploy script: {exc}",
            sha=sha,
            site=site,
        )

    scope = f"site={site}" if site else "all sites"
    return RebuildResponse(
        triggered=True,
        message=f"Spawned {Path(script).name} (SHA={sha[:7]}, {scope}). Poll GET /api/monitor/deploys?project=shared-tube for progress.",
        sha=sha,
        site=site,
    )
