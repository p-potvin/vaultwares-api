import os
import ipaddress
from threading import Lock

# Load dotenv in case it is imported directly
from dotenv import load_dotenv
load_dotenv()

def _env_int_with_floor(name: str, default: int, minimum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return max(value, minimum)

AUTH_ENABLED = os.environ.get("AUTH_ENABLED", "1") == "1"
DEFAULT_MODELS_DIR = os.environ.get("DEFAULT_MODELS_DIR") or os.environ.get("MODELS_DIR")

CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://localhost:4173").split(",")
    if origin.strip()
]

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "vault-server")
JWT_AUDIENCE = os.environ.get("JWT_AUDIENCE", "vaultwares")
JWT_TTL_SECONDS = int(os.environ.get("JWT_TTL_SECONDS", "900"))
API_KEY_PEPPER = os.environ.get("API_KEY_PEPPER") or JWT_SECRET

BOOTSTRAP_ADMIN_USERNAME = os.environ.get("BOOTSTRAP_ADMIN_USERNAME", "")
BOOTSTRAP_ADMIN_PASSWORD = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
BOOTSTRAP_ADMIN_IS_DISABLED = os.environ.get("BOOTSTRAP_ADMIN_IS_DISABLED", "0") == "1"

REQUIRE_HTTPS = os.environ.get("REQUIRE_HTTPS", "1") == "1"
ALLOW_HTTP_TRUSTED = os.environ.get("ALLOW_HTTP_TRUSTED", "1") == "1"

ALLOWED_ORIGINS = set(
    origin.strip()
    for origin in os.environ.get("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
)

TRUSTED_CLIENT_IPS = [
    ip.strip()
    for ip in os.environ.get("TRUSTED_CLIENT_IPS", "").split(",")
    if ip.strip()
]
_trusted_client_ips = []
for _ip in TRUSTED_CLIENT_IPS:
    try:
        _trusted_client_ips.append(ipaddress.ip_address(_ip))
    except ValueError:
        pass

TAILSCALE_CIDRS = [
    cidr.strip()
    for cidr in os.environ.get("TAILSCALE_CIDRS", "100.64.0.0/10,fd7a:115c:a1e0::/48").split(",")
    if cidr.strip()
]
_tailscale_networks = []
for _cidr in TAILSCALE_CIDRS:
    try:
        _tailscale_networks.append(ipaddress.ip_network(_cidr, strict=False))
    except ValueError:
        pass

TRUSTED_PROXY_CIDRS = [
    cidr.strip()
    for cidr in os.environ.get("TRUSTED_PROXY_CIDRS", "127.0.0.1/32,::1/128").split(",")
    if cidr.strip()
]
_trusted_proxy_networks = []
for _cidr in TRUSTED_PROXY_CIDRS:
    try:
        _trusted_proxy_networks.append(ipaddress.ip_network(_cidr, strict=False))
    except ValueError:
        pass

RATE_LIMIT_ENABLED = os.environ.get("RATE_LIMIT_ENABLED", "1") == "1"
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
RATE_LIMIT_MAX_PUBLIC = _env_int_with_floor("RATE_LIMIT_MAX_PUBLIC", 3000, 3000)
RATE_LIMIT_MAX_TRUSTED = _env_int_with_floor("RATE_LIMIT_MAX_TRUSTED", 30000, 30000)
MAINTENANCE_MODE = os.environ.get("MAINTENANCE_MODE", "0") == "1"

GATEWAY_REQUIRED_PUBLIC = os.environ.get("GATEWAY_REQUIRED_PUBLIC", "1") == "1"
GATEWAY_SHARED_SECRET = os.environ.get("GATEWAY_SHARED_SECRET", "")
GATEWAY_HEADER_NAME = os.environ.get("GATEWAY_HEADER_NAME", "x-vw-gateway-secret").lower()

VW_CORRELATION_APP_CODE = os.environ.get("VW_CORRELATION_APP_CODE", "API")
VW_REQUEST_LOG_MODE = os.environ.get("VW_REQUEST_LOG_MODE", "important").strip().lower()
VW_REQUEST_LOG_SLOW_MS = _env_int_with_floor("VW_REQUEST_LOG_SLOW_MS", 2000, 1)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_DIR = os.environ.get("JOBS_DIR") or os.path.join(BASE_DIR, "data", "jobs")
JOB_QUEUE_MAX_PENDING = int(os.environ.get("JOB_QUEUE_MAX_PENDING", "200"))
JOB_WORKER_CONCURRENCY = max(1, int(os.environ.get("JOB_WORKER_CONCURRENCY", "1")))
JOB_DEFAULT_TTL_SECONDS = int(os.environ.get("JOB_DEFAULT_TTL_SECONDS", "86400"))

JOBS_PUBLIC_SUBMIT_ENABLED = os.environ.get("JOBS_PUBLIC_SUBMIT_ENABLED", "0") == "1"
JOB_SUBMIT_RATE_LIMIT_MAX_PUBLIC = _env_int_with_floor("JOB_SUBMIT_RATE_LIMIT_MAX_PUBLIC", 120, 120)
JOB_SUBMIT_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("JOB_SUBMIT_RATE_LIMIT_WINDOW_SECONDS", "60"))

WORKFLOWS_FILE = os.environ.get("WORKFLOWS_FILE", "workflows.json")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
API_KEY_REG_URL = os.environ.get("API_KEY_REG_URL", f"{FRONTEND_URL.rstrip('/')}/register")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_DEFAULT_MODEL = os.environ.get("OLLAMA_DEFAULT_MODEL", "llama3")
OLLAMA_CALL_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_CALL_TIMEOUT_SECONDS", "120"))

COMFYUI_JOB_POLL_INTERVAL_SECONDS = float(os.environ.get("COMFYUI_JOB_POLL_INTERVAL_SECONDS", "2"))
COMFYUI_JOB_MAX_WAIT_SECONDS = float(os.environ.get("COMFYUI_JOB_MAX_WAIT_SECONDS", "600"))

COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
COMFYUI_PROMPT_TIMEOUT_SECONDS = float(os.environ.get("COMFYUI_PROMPT_TIMEOUT_SECONDS", "300"))
COMFYUI_URL_TOKEN_TTL_SECONDS = int(os.environ.get("COMFYUI_URL_TOKEN_TTL_SECONDS", "3600"))

UPLOADS_DIR = os.environ.get("UPLOADS_DIR", "./_uploads")
UPLOADS_MAX_BYTES = int(os.environ.get("UPLOADS_MAX_BYTES", str(20 * 1024 * 1024)))
UPLOADS_TOKEN_TTL_SECONDS = int(os.environ.get("UPLOADS_TOKEN_TTL_SECONDS", "86400"))

COMFYUI_OBJECT_INFO_CACHE_TTL = int(os.environ.get("COMFYUI_OBJECT_INFO_CACHE_TTL", "300"))
HTTP_NODE_TIMEOUT_SECONDS = float(os.environ.get("HTTP_NODE_TIMEOUT_SECONDS", "60"))

DB_URL = os.getenv("DB_URL", "postgres://localhost:5432/vaultwares")

APP_CONFIG = {
    "modelsDir": DEFAULT_MODELS_DIR or "",
    "preferredStorageProvider": "other",
    "apiMode": "remote-with-local-fallback",
    "apiBase": "",
    "themeIndex": 0,
    "runtimeProvider": "local-bridge" if DEFAULT_MODELS_DIR else "browser-local",
    "localBridgeUrl": "http://127.0.0.1:8484",
    "localComfyUrl": "http://127.0.0.1:8188",
    "saveDirectory": "",
    "facefusionCommand": "facefusion",
    "scannedModels": {
        "scannedAt": "",
        "source": "none",
        "modelsDir": DEFAULT_MODELS_DIR or "",
        "warnings": [],
        "categories": {
            "checkpoints": [],
            "loras": [],
            "insightface": [],
            "hyperswap": [],
            "reactorFaces": [],
            "facerestoreModels": [],
            "ultralytics": [],
            "sams": [],
        },
    },
    "flowModelSelections": {
        "imageCaptioning": {"captionModel": "", "captionAdapter": ""},
        "loraTraining": {"baseModel": ""},
        "videoFaceSwap": {
            "swapModel": "",
            "alternateSwapModel": "",
            "faceModel": "",
            "restoreModel": "",
            "detectorModel": "",
        },
    },
}

NGC_API_KEY = os.environ.get("NGC_API_KEY", "")

