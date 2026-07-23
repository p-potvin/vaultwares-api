# Trailer Cache Pipeline — Plan

**Thu, 23 Jul 2026**

## Goal
Stop resolving YouTube trailers per-view (KinoCheck → yt-dlp `--get-url`, whose
googlevideo URLs expire and are slow). Instead, cache each trailer once as a
durable hosted file behind **vaultwares-api**, store the mapping in Postgres, and
have **vault-streaming** ask the API for a ready-to-play URL.

## Why server-side (settled)
Per user: only Real-Debrid is IP-ban sensitive and that's covered by a dedicated
media-stack key; TorBox is fine to call directly. Regardless, the pipeline runs
in the API "as for any other request" so the same pass also writes the DB. The
Comet-only policy (HANDOFF.md) is about torrent/debrid magnet resolution and does
not apply to this upload/caching path.

## Architecture
```
vault-streaming (client)
        │  GET /media/trailer?youtube_id=…&tmdb_id=…&media_type=…
        ▼
vaultwares-api (FastAPI, 127.0.0.1:9001, X-API-Key)
        │  hit?  → return {status:'ready', url}
        │  miss? → INSERT pending, enqueue job, return {status:'pending'}
        ▼
job worker (app.state.job_queue)
        │  1. yt-dlp download → temp mp4 (format 22/18, once)
        │  2. parallel: pixeldrain + gofile + 1fichier  (instant)
        │     → first success sets primary_url, status='ready', ready_at
        │  3. submit to TorBox YouTube cache (slow ~10 min) → poll → torbox_url
        ▼
Postgres trailer_cache  (migrations/trailers/001_trailer_cache.sql)
```

## Endpoint contract  (api/routes_trailers.py — to build)
- `GET /media/trailer?youtube_id=…[&tmdb_id&media_type&title]`, `Depends(require_auth)`
  - `ready`   → `{ status:"ready", youtube_id, url, hosts:{pixeldrain,gofile,onefichier,torbox} }`
  - `pending` → `{ status:"pending", youtube_id }` (client falls back to live yt-dlp meanwhile)
  - `failed`  → `{ status:"failed", error }`
  - on miss: INSERT `pending`, `_queue_job(app, _new_job("trailer_cache", {youtube_id,…}, principal))`, return `pending`
- `POST /media/trailer/refresh` (admin) — force re-cache (re-run pipeline).
- Register in `api/app.py` via `include_router(trailers_router)`.
- Response models in `api/models.py`.

## Data model
`trailer_cache` keyed by `youtube_id`; per-host URL columns + `primary_url`,
`status`, timestamps. Migration already written. Run via the project's migration
path (raw SQL, matching `migrations/telemetry/001_*.sql`).

## Pipeline service  (app/services/trailer_cache.py — to build)
Stage functions, each returning a direct-download URL or raising:
- `download_youtube(youtube_id) -> Path`  — reuse the yt-dlp invocation already
  proven in vault-streaming media.ipc.js (`--format 22/18 --no-playlist
  --extractor-args youtube:player_client=android,web`), writing to disk (not `--get-url`).
- `upload_pixeldrain(path) -> url`   — anonymous `PUT https://pixeldrain.com/api/file/<name>`;
  direct stream at `https://pixeldrain.com/api/file/<id>?download`. **Best for `<video>`** (Range + CORS). No key required (key raises limits).
- `upload_gofile(path) -> url`       — needs account **token**; `getServer` → `uploadFile`; direct link is server/account-scoped.
- `upload_onefichier(path) -> url`   — needs **API key**; note free-tier download throttling makes it a *backup/durable* copy, not the primary stream.
- `submit_torbox(youtube_id) -> url` — TorBox web-download/YouTube endpoint; **async ~10 min**, poll to completion, store as durable `torbox_url`.

Serve preference for `primary_url`: **pixeldrain → gofile → torbox → 1fichier**.

## Client changes  (vault-streaming — to build)
- Add API base + `X-API-Key` to config (currently the app has **no** vaultwares-api
  wiring — needs a base URL, e.g. Tailscale `http://100.73.93.84:9001`, and a key).
- New main-process helper `get-cached-trailer` → calls the API.
- In `js/hover-card.js` (and the TMDB trailer path in `src/tmdb.js`): try the API
  first; on `ready` play `url`; on `pending`/`failed`/unreachable **fall back to the
  existing KinoCheck + `extract-youtube-url` flow** (zero regression).
- Optional: fire-and-forget a warm call when a details modal opens so the trailer
  is cached before the user clicks play.

## Deployment
- Run migration on the API's Postgres.
- Ensure `yt-dlp` present on the API host (greencloud VPS).
- Set host credentials as env/secrets (see below).
- Follow the API repo's deploy-flow (see vaultwares-docs operations/*).

## BLOCKERS — need from user before uploader code can be written/tested
1. **Credentials + where they live** (the app uses `C:\…\.access\*.txt`; API likely uses env):
   - TorBox API key
   - gofile account token
   - 1fichier API key
   - pixeldrain API key (optional but recommended)
2. **App→API auth**: the vault-streaming client has no API base/key today — confirm
   base URL (Tailscale IP:9001?) and issue an `X-API-Key` for it.
3. **Confirm** cache key = YouTube video id (dedupes across TMDB ids that share a trailer).

## Status
- [x] DB migration written (`migrations/trailers/001_trailer_cache.sql`)
- [x] Design captured (this doc)
- [ ] `routes_trailers.py` + models + register  (no creds needed — can start)
- [ ] `app/services/trailer_cache.py` (pixeldrain path can start; others need creds)
- [ ] job kind `trailer_cache` wired into the worker
- [ ] vault-streaming client integration + fallback
- [ ] migration run + deploy
