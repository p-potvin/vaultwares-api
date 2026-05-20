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
- Integration hooks for `vaultwares-adk`

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
- No telemetry
- Full threat model in central [VaultWares docs](https://docs.vaultwares.ca)

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md) and the central [Brand Guidelines](https://raw.githubusercontent.com/p-potvin/vaultwares-docs/main/agents/branding.mdx).

## License
GPL-3.0 (see [LICENSE](LICENSE))

Built with ❤️ for privacy
