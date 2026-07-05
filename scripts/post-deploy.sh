#!/usr/bin/env bash
# vaultwares-api post-deploy hook — runs after `git pull` + `systemctl restart
# vaultwares-api.service` on the OVH host. Writes /var/lib/vw-deploy/status/
# vaultwares-api.json so /api/monitor/deploys can report the live version /
# SHA / systemd state without SSHing or running commands at request time.
#
# Idempotent. Safe to run standalone (e.g. `bash scripts/post-deploy.sh` after
# a manual pull).

set -euo pipefail
LC_ALL=C.UTF-8

REPO_PATH="${REPO_PATH:-/opt/vaultwares-api}"
STATUS_DIR="/var/lib/vw-deploy/status"
STATUS_FILE="${STATUS_DIR}/vaultwares-api.json"
LOG_PATH="${LOG_PATH:-/var/log/vw-deploy/vaultwares-api.log}"
UNIT="${UNIT:-vaultwares-api.service}"

mkdir -p "$STATUS_DIR" "$(dirname "$LOG_PATH")"
END_TS="$(date -Is)"
echo "[$END_TS] vaultwares-api post-deploy" >>"$LOG_PATH"

python3 - "$STATUS_FILE" "$REPO_PATH" "$LOG_PATH" "$UNIT" "$END_TS" <<'PY'
import json, os, subprocess, sys, tempfile

(dest, repo, log_path, unit, ts) = sys.argv[1:]

def run(cmd, timeout=3):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout).stdout.strip()
    except Exception:
        return ""

def read_pyproject_version(p):
    path = os.path.join(p, "pyproject.toml")
    if not os.path.exists(path):
        return ""
    for line in open(path):
        if line.strip().startswith("version"):
            # `version = "0.1.15"` → 0.1.15
            parts = line.split("=", 1)
            if len(parts) == 2:
                return parts[1].strip().strip('"').strip("'")
    return ""

sha = run(["git", "-C", repo, "rev-parse", "--short=7", "HEAD"])
py_version = read_pyproject_version(repo)
active = run(["systemctl", "show", unit, "-p", "ActiveState", "--value"])
since = run(["systemctl", "show", unit, "-p", "ActiveEnterTimestamp", "--value"])

# Grab the running app version from the FastAPI title, since app.py's
# `version="0.2.x"` may drift from pyproject.toml.
api_version = ""
try:
    with open(os.path.join(repo, "api", "app.py")) as f:
        for line in f:
            s = line.strip()
            if s.startswith("version="):
                api_version = s.split("=", 1)[1].strip().rstrip(",").strip('"').strip("'")
                break
except Exception:
    pass

# Tail the log for context.
log_tail = []
try:
    with open(log_path) as f:
        log_tail = f.read().splitlines()[-40:]
except Exception:
    pass

status = {
    "project": "vaultwares-api",
    "repo_sha": sha,
    "api_version": api_version or py_version,
    "pyproject_version": py_version,
    "log_path": log_path,
    "targets": [
        {
            "id": "vaultwares-api",
            "site": None,
            "version": api_version or py_version,
            "sha": sha,
            "systemd": {"unit": unit, "active": active, "since": since},
        }
    ],
    "last_build": {
        "phase": "ok",
        "sha": sha,
        "site": None,
        "started_at": ts,
        "finished_at": ts,
        "duration_s": 0,
        "exit_code": 0,
        "ok": True,
    },
    "log_tail": log_tail,
}
tmp = dest + ".tmp"
with open(tmp, "w") as f:
    json.dump(status, f, indent=2)
os.replace(tmp, dest)
print(f"wrote {dest}: version={status['api_version']} sha={sha} active={active}")
PY
