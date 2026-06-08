# VPS Gateway Plan (Tailscale -> Local API)

Goal: keep `vaultwares-pipelines` running on your local PC, while exposing a single public entrypoint
(`api.vaultwares.ca`) from a VPS that forwards traffic over your tailnet. Your PC never needs to be
publicly reachable from the internet.

## Architecture (high level)

- Public client (browser / Vercel site)
  -> HTTPS -> VPS (Nginx + real TLS cert)
  -> Tailscale (private network)
  -> Local PC (FastAPI on port 9001 + Postgres)

## Noddit (Vault Flows) same-origin proxy

For `noddit.org`, prefer a split reverse-proxy so the browser only ever talks to `https://noddit.org`:

- `/` → Vault Flows SPA on the PC (tailnet `:3100`)
- `/api/` → Pipelines API on the PC (tailnet `:9001`)

This avoids mixed-content warnings and avoids exposing tailnet IPs to the browser.

Example config: `noddit_vps_nginx.conf.example`.

## Why this matches the "hidden API" goal

- The only internet-exposed service is the VPS (you can add strict limits there quickly).
- Your local API can reject anything that is not:
  - localhost
  - your tailnet (Tailscale)
  - or a gateway-proxied request that includes the shared gateway secret header

## Step 1: Join the VPS to your tailnet

1. Install Tailscale on the VPS.
2. Run `tailscale up` and confirm:
   - the VPS gets a `100.x.y.z` address (and optionally a MagicDNS name)
   - the VPS can reach your PC's Tailscale IP on port `9001`

## Step 2: Run the API on your local PC

- Keep `API_PORT=9001`.
- Bind `API_HOST=0.0.0.0` so the API is reachable via the Tailscale interface.
- Do NOT port-forward `9001` from your router.
- Optional hardening: add a Windows firewall rule that only allows inbound TCP/9001 from Tailscale.

## Step 3: Configure the API for a VPS proxy

In your local `.env` (based on `.env.local-api.example`):

- Set `GATEWAY_SHARED_SECRET` to a long random value.
- Set `TRUSTED_PROXY_CIDRS` to the VPS Tailscale IP, so `X-Forwarded-For` cannot be spoofed:

```env
TRUSTED_PROXY_CIDRS=100.73.57.6/32,127.0.0.1/32,::1/128
```

- Set `TRUSTED_CLIENT_IPS` to the exact Tailnet devices that should be treated as trusted:

```env
TRUSTED_CLIENT_IPS=100.67.153.112,100.71.101.21,100.91.249.45,100.75.112.67,100.73.57.6
```

Notes:
- Leave `TAILSCALE_CIDRS` at the default unless your tailnet uses non-standard ranges.
- Keep `REQUIRE_HTTPS=1`. The VPS sets `X-Forwarded-Proto: https` so the API treats it as HTTPS.
- Keep `ALLOW_HTTP_TRUSTED=1` so the VPS can talk to the API over plain HTTP on the tailnet.

## Step 4: Configure Nginx on the VPS

Start from `vps_nginx.conf.example`:
- Set `server_name` to your real domain (e.g., `api.vaultwares.ca`).
- Point `proxy_pass` to your local PC's Tailscale IP (or MagicDNS name).
- Inject `X-VW-Gateway-Secret` to match `GATEWAY_SHARED_SECRET` on the API.

## Step 5: Point Vercel apps at the VPS domain

- Set your frontend `API_BASE` (or env var) to `https://api.vaultwares.ca`.
- Keep all direct API traffic going to the VPS, never to your home IP.
- On the API host, set `ALLOWED_ORIGINS` to your stable Vercel app domains so `/auth/login` only works from your sites.

## Traffic verification

Use the built-in diagnostics endpoint after deployment:

```bash
curl https://api.vaultwares.ca/diagnostics/network \
  -H "Authorization: Bearer <admin-jwt>"
```

For a request that came through the VPS gateway, the response should show:
- `served_by` = your local PC hostname
- `peer_ip` = `100.73.57.6`
- `via_trusted_proxy` = `true`

## Quick abuse controls (edge + API)

VPS:
- Nginx `limit_req` (fast throttle)
- optional IP allow/deny rules
- temporary `return 503` maintenance block

API:
- `RATE_LIMIT_*` and `MAINTENANCE_MODE`
- revoke API keys (`api_keys.is_revoked`)
- shorten `JWT_TTL_SECONDS` during an incident

## Future: second machine + load balancing

When you add a second API host, the VPS can:
- send traffic to multiple Tailscale upstreams (simple round-robin)
- or you can move more routing into the tailnet (e.g., an exit node / dedicated internal gateway)
