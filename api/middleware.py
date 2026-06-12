import logging
import os
import re
import socket
import secrets
import time
from urllib.parse import urlparse
from datetime import datetime, timezone
import requests
import threading
from collections import deque
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from api.config import (
    VW_CORRELATION_APP_CODE, VW_REQUEST_LOG_MODE, VW_REQUEST_LOG_SLOW_MS,
    MAINTENANCE_MODE, REQUIRE_HTTPS, ALLOW_HTTP_TRUSTED, GATEWAY_REQUIRED_PUBLIC,
    GATEWAY_SHARED_SECRET, GATEWAY_HEADER_NAME, RATE_LIMIT_ENABLED,
    RATE_LIMIT_WINDOW_SECONDS, RATE_LIMIT_MAX_TRUSTED, RATE_LIMIT_MAX_PUBLIC,
    ALLOWED_ORIGINS
)
from api.auth import _get_client_ip, _is_trusted_client_ip, _effective_scheme

logger = logging.getLogger("vaultwares.api")

class KiwiLogHandler(logging.Handler):
    def __init__(
        self,
        target_url=None,
        max_batch_size=None,
        flush_interval=None,
        syslog_host=None,
        syslog_port=None,
        transport=None,
        start_worker=True,
    ):
        super().__init__()
        self.target_url = target_url or os.environ.get("VW_KIWI_LOG_URL")
        self.transport = (transport or os.environ.get("VW_KIWI_LOG_TRANSPORT") or ("http_json" if self.target_url else "syslog_udp")).lower()
        self.syslog_host = syslog_host or os.environ.get("VW_KIWI_SYSLOG_HOST", "127.0.0.1")
        self.syslog_port = int(syslog_port or os.environ.get("VW_KIWI_SYSLOG_PORT", "514"))
        self.max_batch_size = int(max_batch_size or os.environ.get("VW_KIWI_LOG_BATCH_SIZE", "25"))
        self.flush_interval = float(flush_interval or os.environ.get("VW_KIWI_LOG_FLUSH_SECONDS", "2.0"))
        self.lock = threading.RLock()
        self.batch = []
        self.first_log_time = None
        self.thread = None

        if start_worker:
            self.thread = threading.Thread(target=self._flush_loop, daemon=True)
            self.thread.start()

    def emit(self, record):
        if record.name.startswith(("urllib3", "requests", "httpx")):
            return
        try:
            msg = self.format(record)
            timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
            
            with self.lock:
                if not self.batch:
                    self.first_log_time = time.time()
                self.batch.append({
                    "timestamp": timestamp,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": msg,
                    "correlationId": getattr(record, "correlation_id", None),
                    "method": getattr(record, "method", None),
                    "path": getattr(record, "path", None),
                    "status_code": getattr(record, "status_code", None),
                    "duration_ms": getattr(record, "duration_ms", None),
                    "source_app": getattr(record, "source_app", None),
                    "client_ip": getattr(record, "client_ip", None),
                    "peer_ip": getattr(record, "peer_ip", None),
                    "origin": getattr(record, "origin", None),
                    "user_agent": getattr(record, "user_agent", None),
                })
                
                if len(self.batch) >= self.max_batch_size:
                    self._flush_now()
        except Exception:
            self.handleError(record)

    def _flush_now(self):
        if not self.batch:
            return
        payload = self.batch
        self.batch = []
        self.first_log_time = None
        
        def send_http_json():
            try: requests.post(self.target_url, json=payload, timeout=3)
            except: pass

        def send_syslog_udp():
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    for item in payload:
                        line = self._format_syslog_line(item)
                        sock.sendto(line.encode("utf-8", errors="replace"), (self.syslog_host, self.syslog_port))
            except: pass

        if self.transport == "http_json" and self.target_url:
            target = send_http_json
        else:
            target = send_syslog_udp
        threading.Thread(target=target, daemon=True).start()

    def _flush_loop(self):
        while True:
            time.sleep(1.0)
            with self.lock:
                if self.batch and (time.time() - self.first_log_time >= self.flush_interval):
                    self._flush_now()

    @staticmethod
    def _syslog_value(value) -> str:
        text = str(value if value not in (None, "") else "-")
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("]", "\\]").replace("\r", " ").replace("\n", " ")

    def _format_syslog_line(self, item: dict) -> str:
        corr = self._syslog_value(item.get("correlationId"))
        method = self._syslog_value(item.get("method"))
        path = self._syslog_value(item.get("path"))
        status = self._syslog_value(item.get("status_code"))
        duration = self._syslog_value(item.get("duration_ms"))
        source = self._syslog_value(item.get("source_app"))
        client_ip = self._syslog_value(item.get("client_ip"))
        peer_ip = self._syslog_value(item.get("peer_ip"))
        origin = self._syslog_value(item.get("origin"))
        message = str(item.get("message") or "").replace("\r", " ").replace("\n", " ")
        return (
            f"<14>1 {item['timestamp']} vaultwares-api vaultwares-api - - "
            f"[vaultwares correlationId=\"{corr}\" source=\"{source}\" method=\"{method}\" path=\"{path}\" "
            f"status=\"{status}\" durationMs=\"{duration}\" clientIp=\"{client_ip}\" peerIp=\"{peer_ip}\" origin=\"{origin}\"] "
            f"{message}"
        )

# Register logging setup
kiwi_handler = KiwiLogHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
kiwi_handler.setFormatter(formatter)
root_logger = logging.getLogger()
root_logger.addHandler(kiwi_handler)

def _normalize_vaultwares_app_code(value: str | None) -> str:
    code = re.sub(r"[^A-Za-z0-9]", "", value or "").upper()
    if len(code) < 3: return "API"
    if len(code) > 4: return code[:4]
    return code

def _new_vaultwares_correlation_id() -> str:
    app_code = _normalize_vaultwares_app_code(VW_CORRELATION_APP_CODE)
    return f"vw_{app_code}_c{secrets.token_hex(4)[:7]}"

def _resolve_correlation_id(request: Request) -> str:
    corr_id = request.query_params.get("correlationId")
    if not corr_id:
        corr_id = request.query_params.get("cID") or request.query_params.get("cid")
    if not corr_id:
        corr_id = getattr(request.state, "correlation_id", None)
    if not corr_id:
        corr_id = request.headers.get("x-correlation-id") or request.headers.get("x-request-id")
    if not corr_id:
        corr_id = _new_vaultwares_correlation_id()
    request.state.correlation_id = corr_id
    return corr_id

_rate_state = deque()
RATE_LIMIT_MAX_STATE_SIZE = 10000
_rate_limits = {}

def _request_source_app(request: Request) -> str:
    for key in ("sourceApp", "source", "app"):
        value = request.query_params.get(key)
        if value: return value[:80]
    for key in ("x-vw-source", "x-source-app", "x-client-name"):
        value = request.headers.get(key)
        if value: return value[:80]
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        try:
            parsed = urlparse(origin)
            if parsed.hostname: return parsed.hostname[:80]
        except:
            return origin[:80]
    return "unknown"

def _request_log_mode_all() -> bool:
    return VW_REQUEST_LOG_MODE in {"all", "debug", "verbose"}

def _request_log_enabled() -> bool:
    return VW_REQUEST_LOG_MODE not in {"0", "false", "off", "none"}

def _should_log_request(status_code: int, duration_ms: float) -> bool:
    if not _request_log_enabled(): return False
    if _request_log_mode_all(): return True
    return status_code >= 400 or duration_ms >= VW_REQUEST_LOG_SLOW_MS

def _origin_allowed(origin: str) -> bool:
    if not origin: return False
    if origin in ALLOWED_ORIGINS: return True
    from api.app import _cors_allow_origins
    if origin in _cors_allow_origins: return True
    return False

def _gateway_secret_valid(request: Request) -> bool:
    if not GATEWAY_SHARED_SECRET: return False
    provided = request.headers.get(GATEWAY_HEADER_NAME, "")
    if not provided: return False
    return secrets.compare_digest(provided, GATEWAY_SHARED_SECRET)

async def gate_requests_middleware(request: Request, call_next):
    correlation_id = _resolve_correlation_id(request)
    method = request.method
    path = request.url.path
    started = time.perf_counter()
    peer_ip = request.client.host if request.client else None
    origin = request.headers.get("origin", "")
    user_agent = request.headers.get("user-agent", "")
    source_app = _request_source_app(request)
    client_ip = ""
    try:
        if len(_rate_limits) > RATE_LIMIT_MAX_STATE_SIZE:
            oldest_key = next(iter(_rate_limits))
            _rate_limits.pop(oldest_key, None)

        client_ip = _get_client_ip(request) or ""
        is_trusted_ip = _is_trusted_client_ip(client_ip)
        if _request_log_mode_all():
            logger.info(
                "request.start",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                    "client_ip": client_ip,
                    "peer_ip": peer_ip,
                    "origin": origin,
                    "user_agent": user_agent,
                    "source_app": source_app,
                    "trusted_client": is_trusted_ip,
                },
            )

        if MAINTENANCE_MODE and not is_trusted_ip:
            raise HTTPException(status_code=503, detail="Temporarily unavailable")

        scheme = _effective_scheme(request)
        if REQUIRE_HTTPS and scheme != "https" and not (ALLOW_HTTP_TRUSTED and is_trusted_ip):
            raise HTTPException(status_code=426, detail="HTTPS required")

        if not is_trusted_ip:
            if GATEWAY_REQUIRED_PUBLIC:
                if not GATEWAY_SHARED_SECRET:
                    raise HTTPException(status_code=500, detail="Gateway secret is not configured")
                if not _gateway_secret_valid(request):
                    raise HTTPException(status_code=403, detail="Forbidden source")
            else:
                if not origin or not _origin_allowed(origin):
                    raise HTTPException(status_code=403, detail="Forbidden source")

        if RATE_LIMIT_ENABLED:
            is_media_pipeline = path in ["/health", "/scrape", "/download", "/abort", "/api/abort", "/api/jobs"]
            if not is_media_pipeline:
                now = time.time()
                key = f"{client_ip}:{origin}" if origin else client_ip
                if key not in _rate_limits:
                    _rate_limits[key] = deque()
                bucket = _rate_limits[key]
                while bucket and (now - bucket[0]) > RATE_LIMIT_WINDOW_SECONDS:
                    bucket.popleft()
                limit = RATE_LIMIT_MAX_TRUSTED if is_trusted_ip else RATE_LIMIT_MAX_PUBLIC
                if len(bucket) >= limit:
                    raise HTTPException(status_code=429, detail="Rate limit exceeded")
                bucket.append(now)

        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)

        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Correlation-Id"] = correlation_id
        
        if _should_log_request(response.status_code, duration_ms):
            logger.info(
                "request.complete",
                extra={
                    "correlation_id": correlation_id,
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "peer_ip": peer_ip,
                    "origin": origin,
                    "user_agent": user_agent,
                    "source_app": source_app,
                    "trusted_client": is_trusted_ip,
                },
            )
        return response
    except HTTPException as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning(
            "request.blocked",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "status_code": exc.status_code,
                "duration_ms": duration_ms,
                "client_ip": client_ip,
                "peer_ip": peer_ip,
                "origin": origin,
                "user_agent": user_agent,
                "source_app": source_app,
                "reason": exc.detail,
            },
        )
        response = JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        response.headers["X-Correlation-Id"] = correlation_id
        return response
    except Exception:
        try: client_ip = _get_client_ip(request)
        except: client_ip = None
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request.crashed",
            extra={
                "correlation_id": correlation_id,
                "method": method,
                "path": path,
                "status_code": 500,
                "duration_ms": duration_ms,
                "peer_ip": peer_ip,
                "client_ip": client_ip,
                "origin": origin,
                "user_agent": user_agent,
                "source_app": source_app,
            },
        )
        response = JSONResponse(status_code=500, content={"detail": "Internal Server Error"})
        response.headers["X-Correlation-Id"] = correlation_id
        return response

async def correlation_id_middleware(request: Request, call_next):
    corr_id = _resolve_correlation_id(request)
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = corr_id
    return response

gate_requests = gate_requests_middleware
