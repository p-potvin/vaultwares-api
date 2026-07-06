<img src="https://raw.githubusercontent.com/p-potvin/vaultwares-docs/main/logo/vaultwares-logo.svg">

# vaultwares-api

**Core VaultWares API and AI/Media Orchestration Engine**
**Part of the VaultWares Ecosystem** • <a href="https://docs.vaultwares.ca">docs.vaultwares.ca</a> • <a href="https://vaultwares.ca">vaultwares.ca</a>

**Owns VaultWares auth, DB-backed telemetry, normalized monitor APIs, logging integration, and multimodal AI/media orchestration with local-first privacy guarantees.**

## Overview
This repository powers the VaultWares API, formerly `vaultwares-pipelines`. It defines the API layer used by VaultWares apps for auth, DB access, telemetry ingest, normalized monitor reads, logging, and complex media transformation pipelines.

All pipelines are designed local-first but support optional remote model endpoints.

## Features
- Modular pipeline definitions (YAML + Python)
- Multimodal model orchestration (image enhancement, STT, face manipulation, video generation)
- LoRA / digital twin support
- Real-time encrypted filters
- Dependency graph execution
- Agent-aware pipeline monitoring
- V.A.U.L.T Monitor telemetry ingest and normalized read APIs
- Integration hooks for `vaultwares-adk`

## Monitor Telemetry API

`vaultwares-api` owns the API and storage path for V.A.U.L.T Monitor and
the agent-ledger input tracker:

- `POST /api/telemetry/input/batches`
- `GET /api/telemetry/input/summary`
- `GET /api/telemetry/input/events/search`
- `POST /api/ledger/agent/events`
- `POST /api/ledger/agent/events/batches`
- `GET /api/ledger/agent/changes`
- `GET /api/ledger/agent/work-impact`
- `GET /api/ledger/agent/events/search`
- `GET /monitor/input-tracker`
- `GET /monitor/changes`
- `GET /monitor/work-impact`

Set these environment variables for local input telemetry:

```bash
VW_TELEMETRY_DATABASE_URL=postgres://postgres:postgres@localhost:5432/vaultwares
VW_TELEMETRY_API_KEY=
VW_TELEMETRY_REQUIRE_KEY=1
VW_TELEMETRY_BATCH_MAX_EVENTS=500
VW_TELEMETRY_AUTO_SCHEMA=1
```

Apply the telemetry schema explicitly with:

```bash
python scripts/apply-telemetry-migrations.py
```

Input tracker clients batch privacy-safe aggregate metrics to this API. They do
not connect to Postgres directly. Replay is idempotent through `batch_id` and
`event_id`.

Agent-ledger clients keep append-only JSON event files as local evidence, but
live dashboards read the Postgres-backed API. Historical event files are
backfilled through `POST /api/ledger/agent/events/batches`; new events are
posted one at a time by `agent-ledger/scripts/record-agent-change.ps1`.

## Correlation IDs and Logging

VaultWares apps must create or preserve a correlation ID when they initiate a
request and pass it as the `correlationId` query parameter until that request
finishes at the API boundary. Headers are accepted only as compatibility
fallbacks.

VaultWares-generated IDs use:

```text
vw_{JIRA_CODE}_c{7_hex_chars}
```

For this service, the default generated form is `vw_API_c123abc4`. Other
brands can use their own prefix and Jira/product code, such as
`pk_PKT_c123456h` for Prom King.

Continuous connections such as streams and downloads may start a new child
correlation ID for long-lived work, but ordinary request/response calls should
keep the original ID from client creation through API completion.

Request logging defaults to important events only: blocked requests, crashes,
HTTP errors, and slow requests. Set these variables to tune volume:

```bash
VW_REQUEST_LOG_MODE=important  # important | all | off
VW_REQUEST_LOG_SLOW_MS=2000
VW_CORRELATION_APP_CODE=API
```

## Workflow Job Queue

Vault-flows ComfyUI workflow jobs are queued and executed one at a time by
`vaultwares-api`, regardless of the client IP that submitted them. This keeps
local GPU/ComfyUI work serialized so the desktop does not run concurrent heavy
jobs.

`/flows/run` waits for the queued ComfyUI job and returns the result to
vault-flows. For services that enqueue work asynchronously, workflow jobs may
include `callbackUrl`; the API sends one completion callback after the job
finishes. Callback URLs are limited to loopback, private, or tailnet hosts by
default.

## Quick Start

```bash
git clone https://github.com/p-potvin/vaultwares-api.git
cd vaultwares-api
git submodule update --init --recursive
pip install -r requirements.txt
python run_pipeline.py --config examples/video_enhance.yaml
```

## Prom-King TPDB Enrichment

To enrich existing videos in the Prom-King database with tags from TPDB (Categories, Performers, Studios), run the backlog script on the server with direct database access:

```bash
# Enrich up to 1000 videos
cd /srv/repos/p-potvin/vaultwares-api
python3 scripts/enrich_backlog.py --limit 1000

# uv run python scripts/enrich_backlog.py --limit 1000

# Specify site and starting ID
uv run python scripts/enrich_backlog.py --site sexyprn --start-id 500
```
New videos are automatically enriched during the fetch pipeline.

## Architecture & Agent Integration
Fully synchronized with the VaultWares Agent Knowledge Dissemination System.
- Agents automatically pull latest branding and guidelines from: → https://raw.githubusercontent.com/p-potvin/vaultwares-docs/main/agents/knowledge-dissemination.mdx
- See full details: [Agent Knowledge System](https://raw.githubusercontent.com/p-potvin/vaultwares-docs/main/agents/knowledge-dissemination.mdx)

## Pipeline Examples
- `examples/video_transcribe_translate.yaml`
- `examples/image_to_video.yaml`
- `examples/realtime_filter.yaml`

## Privacy & Security
- Local-first execution by default
- Encrypted intermediate artifacts
- No raw typed text, clipboard contents, secrets, or unhashed window titles in
  input telemetry
- Full threat model in central [VaultWares docs](https://docs.vaultwares.ca)

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) and the central [Brand Guidelines](https://raw.githubusercontent.com/p-potvin/vaultwares-docs/main/agents/branding.mdx).

## License
GPL-3.0 (see [LICENSE](LICENSE))

Built with ❤️ for privacy

## Prom-King

To enrich the Prom-King backlog with metadata, run the following script:

```bash
uv run scripts/enrich_backlog.py --limit 1000
```
