"""
Rebuild endpoint — triggers a fresh Astro build + service restart for the
shared-tube apps.

Any change that affects prerender output (e.g. new head/body tags injected
via the Marketing settings) needs a fresh build. Push-to-main normally
triggers this via vw-webhookd; this endpoint gives the admin operator a
manual button when they've edited settings and don't want to bump git.

The endpoint runs the same deploy script vw-webhookd would use:
    /var/www/deploy-scripts/deploy-shared-tube.sh
    with SHA=<current-HEAD-of-/srv/repos/Prom-King/shared-tube>

Requires the FastAPI process user to have exec permission on the script.
In production that's granted via ops (sudoers/group). If the script isn't
found or isn't executable, the endpoint returns triggered=false with a
descriptive message rather than raising.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from ._models import Site

router = APIRouter(tags=["promking:rebuild"])


DEFAULT_DEPLOY_SCRIPT = "/var/www/deploy-scripts/deploy-shared-tube.sh"
DEFAULT_REPO_PATH = "/srv/repos/Prom-King/shared-tube"


class RebuildRequest(BaseModel):
    # `site` is accepted for future scoping but currently ignored — the deploy
    # script rebuilds and restarts every site's systemd service at once.
    # Keeping the field lets the admin panel evolve without a schema break.
    site: Optional[Site] = None


class RebuildResponse(BaseModel):
    triggered: bool
    message: str
    sha: Optional[str] = None


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


@router.post("/rebuild", response_model=RebuildResponse)
async def rebuild(_req: RebuildRequest) -> RebuildResponse:
    """
    Fire-and-forget: spawn deploy-shared-tube.sh as a detached subprocess and
    return immediately. The admin panel toasts "triggered" and the actual
    build takes ~30-90s depending on the host. Progress lives in
    /var/log/vw-deploy/shared-tube.log — the operator can tail it from the
    SQL tab or ops SSH.
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

    env = os.environ.copy()
    env["SHA"] = sha
    env["VW_AFTER"] = sha

    # Detach: parent-agnostic, no PIPE (script logs to /var/log directly).
    # This means we don't wait for or watch stdout — that's by design; the
    # admin panel is fire-and-forget.
    try:
        await asyncio.create_subprocess_exec(
            script,
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
        )

    return RebuildResponse(
        triggered=True,
        message=f"Spawned {Path(script).name} (SHA={sha[:7]}). Tail /var/log/vw-deploy/shared-tube.log for progress.",
        sha=sha,
    )
