## Starting the API Server (FastAPI)

You can run the API server using the provided `api_server.py` file. This will start a FastAPI server exposing all workflow endpoints.

### 1. Install dependencies (if not already done):
```bash
pip install -r requirements.txt
```

### 2. (Recommended) Activate your virtual environment:
```bash
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate
```

### 3. Start the API server:
```bash
python api_server.py
```

- By default, the server will run on `http://127.0.0.1:9001` (see `api_server.py` entrypoint).
- The OpenAPI/Swagger UI will be available at `http://127.0.0.1:9001/docs`.
- You can configure CORS, auth, source allowlists, and rate limits via environment variables (see top of `api_server.py`).

---

## Authentication (API key + JWT)

This API supports:
- **JWT** for user sessions (browser clients)
- **X-API-Key** for trusted-network automation (localhost / Tailscale only)

Required env vars for JWT:
```env
JWT_SECRET=change-me
JWT_ISSUER=vault-server
JWT_AUDIENCE=vaultwares
JWT_TTL_SECONDS=900
```

Bootstrap one admin user (optional, for initial setup):
```env
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_PASSWORD=change-me
```

Create an API key (admin JWT required, trusted network only):
- `POST /auth/login` -> bearer token
- `POST /auth/api-keys` with JSON `{ "name": "my-key" }` -> returns `api_key` once

---

## Strict source allowlist (Vercel + localhost + Tailscale)

Set stable Vercel app origins (not preview URLs):
```env
ALLOWED_ORIGINS=https://vaultwares-dispatch-frontend.vercel.app,https://vaultwares-glass-preview.vercel.app
```

Note: `/auth/login` requires an allowlisted `Origin` so only your frontends can initiate sessions.

For stronger protection (recommended), require public-internet requests to pass through a gateway
(recommended: a VPS that forwards to your local API over Tailscale) that adds a shared secret header:
```env
GATEWAY_REQUIRED_PUBLIC=1
GATEWAY_SHARED_SECRET=change-me-long-random
```

Your gateway must send `X-VW-Gateway-Secret: <secret>` when proxying to the API.
If you want a different header name:
```env
GATEWAY_HEADER_NAME=x-vw-gateway-secret
```

See `vps_nginx.conf.example` for a VPS-friendly Nginx config (TLS termination + proxy over Tailscale).

### VPS gateway (recommended) quick start

1. Install Tailscale on the VPS and join it to your tailnet.
2. Point Nginx upstream to your local PC's **Tailscale** address (not your LAN IP).
3. Inject `X-VW-Gateway-Secret` on the VPS when proxying to the API.
4. On the API host, set `TRUSTED_PROXY_CIDRS` to your VPS Tailscale IP (so X-Forwarded-For can't be spoofed).

Example:
```env
TRUSTED_PROXY_CIDRS=100.73.57.6/32,127.0.0.1/32,::1/128
```

If you want to trust only known Tailnet devices instead of the full Tailnet range, set an exact IP allowlist:
```env
TRUSTED_CLIENT_IPS=100.67.153.112,100.71.101.21,100.91.249.45,100.75.112.67,100.73.57.6
```

### Brume 2 (OpenWrt) Nginx (optional alternative)

1. Copy the example to your Brume (adjust as needed for your Nginx install):
   - Common locations: `/etc/nginx/conf.d/vaultwares-api.conf` or `/etc/nginx/sites-enabled/vaultwares-api.conf`
   - Ensure it’s included by your main `/etc/nginx/nginx.conf` (you can verify with `nginx -T`).
2. Replace `<GATEWAY_SHARED_SECRET>` with the same value used on the API host.
3. Set `ssl_certificate` / `ssl_certificate_key` to the files created by your ACME client.
   - `luci-app-acme` / `acme.sh` commonly uses `/etc/acme/<domain>/...` (see comments in `brume2_nginx.conf.example`).
4. Validate and reload:
   - `nginx -t`
   - `/etc/init.d/nginx reload` (or restart if reload isn’t supported)

Tailscale networks (defaults to `100.64.0.0/10` and `fd7a:115c:a1e0::/48`):
```env
TAILSCALE_CIDRS=100.64.0.0/10,fd7a:115c:a1e0::/48
```

When using a LAN gateway (like Brume) over your local network, run the API bound to LAN:
```env
API_HOST=0.0.0.0
API_PORT=9001
UVICORN_RELOAD=1
```

---

## Rate limiting (quick abuse controls)

```env
RATE_LIMIT_ENABLED=1
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_MAX_PUBLIC=120
RATE_LIMIT_MAX_TRUSTED=1200
```

Emergency switch (blocks public internet, still allows localhost/Tailscale):
```env
MAINTENANCE_MODE=1
```

---

**Note:** If you want to run the API with production features (e.g., hot reload, multiple workers), you can use `uvicorn`:
```bash
pip install uvicorn
uvicorn api_server:app --reload --port 8000
```

---

## Real TLS + HTTPS enforcement (recommended)

Run FastAPI on loopback and terminate TLS in a local reverse proxy (Caddy or Nginx).
The API enforces HTTPS by default for non-trusted networks (`REQUIRE_HTTPS=1`).

High-level setup:
1. Point `api.yourdomain.com` to your home IP (Dynamic DNS if needed).
2. Forward ports `80`/`443` to the machine running the reverse proxy.
3. Configure the proxy to forward to `http://127.0.0.1:9001` and set `X-Forwarded-Proto: https`.

See `Caddyfile.example` for a minimal Caddy config.

If you run behind a reverse proxy, ensure the API only trusts `X-Forwarded-For` from that proxy:
```env
TRUSTED_PROXY_CIDRS=10.0.0.50/32,127.0.0.1/32,::1/128
```

## Traffic verification

After deploying the VPS gateway, verify that public traffic is actually reaching your local PC through the Tailnet:

```bash
curl https://api.vaultwares.ca/diagnostics/network \
  -H "Authorization: Bearer <admin-jwt>"
```

Expected signals in the JSON response:
- `served_by` should be your local PC hostname, such as `clopeux-desktop`
- `peer_ip` should be `100.73.57.6`
- `via_trusted_proxy` should be `true`
- `effective_scheme` should be `https`
- `client_ip` should be the original caller, not the VPS

If you call the same endpoint directly from a trusted Tailnet device instead of through the public domain, `peer_ip` will be that device and `via_trusted_proxy` will be `false`.

---

## Local TLS with mkcert (recommended for Windows development)

Use mkcert to run the API locally over real HTTPS while keeping the certificates out of git.

### Generate certificates

```powershell
.\generate_local_tls_certs.ps1
```

This creates:

- `.certs/localhost+127.0.0.1.pem`
- `.certs/localhost+127.0.0.1-key.pem`

### Start the local HTTPS API

```powershell
.\start_https_dev.ps1
```

Recommended local frontend origin:

- `https://localhost:5174`

Recommended local API base:

- `https://localhost:8000`

If you need a different port, set `API_PORT` before running the script.

---

