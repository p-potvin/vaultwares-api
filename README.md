<img src="https://raw.githubusercontent.com/p-potvin/vaultwares-docs/main/logo/vaultwares-logo.svg">

# vaultwares-pipelines

**Core AI/Media Orchestration Engine**  
**Part of the VaultWares Ecosystem** • <a href="https://docs.vaultwares.ca">docs.vaultwares.ca</a> • <a href="https://vaultwares.ca">vaultwares.ca</a>

**Orchestrates multimodal AI pipelines (video, image, audio, LoRAs, digital twins, I2V/T2V, real-time filters) with local-first privacy guarantees.**

## Overview
This repository powers the VaultWares AI backbone. It defines, runs, and monitors complex media transformation pipelines that feed into `vault-flows`, `vault-player`, `vaultwares-realtime`, and other components.

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

`vaultwares-pipelines` owns the API and storage path for V.A.U.L.T Monitor and
the agent-ledger input tracker:

- `POST /api/telemetry/input/batches`
- `GET /api/telemetry/input/summary`
- `GET /api/telemetry/input/events/search`
- `GET /monitor/input-tracker`

Set these environment variables for local input telemetry:

```bash
VW_TELEMETRY_DATABASE_URL=postgres://postgres:postgres@localhost:5432/vaultwares
VW_TELEMETRY_API_KEY=
VW_TELEMETRY_REQUIRE_KEY=1
VW_TELEMETRY_BATCH_MAX_EVENTS=500
VW_TELEMETRY_AUTO_SCHEMA=1
```

Input tracker clients batch privacy-safe aggregate metrics to this API. They do
not connect to Postgres directly. Replay is idempotent through `batch_id` and
`event_id`.

## Quick Start

```bash
git clone https://github.com/p-potvin/vaultwares-pipelines.git
cd vaultwares-pipelines
git submodule update --init --recursive
pip install -r requirements.txt
python run_pipeline.py --config examples/video_enhance.yaml
```

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
