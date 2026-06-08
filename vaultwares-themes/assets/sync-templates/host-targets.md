# Sync targets — host file map

The `MANAGED` block from `managed-block.md` is **identical content** across every host. Only the filename differs. This file is the authoritative map for `theme-manager/tools/sync_submodule_rules.py`.

## File map

| Host / IDE | File path in each consumer repo | Notes |
| --- | --- | --- |
| **Claude Code · Claude.ai chat** | `CLAUDE.md` | Project root only; subfolders ignored. |
| **OpenAI Codex CLI · `vaultwares-cli`** | `AGENTS.md` | Same convention as `vault-themes` itself. |
| **Cursor** | `.cursor/rules/vaultwares.mdc` | New format (multi-file rules). Legacy fallback: `.cursorrules`. |
| **Windsurf** | `.windsurf/rules/vaultwares.md` | Legacy fallback: `.windsurfrules`. |
| **GitHub Copilot** | `.github/copilot-instructions.md` | Single-file convention. |
| **Continue** | `.continue/rules/vaultwares.md` | One file per topic, auto-merged. |
| **Aider** | `CONVENTIONS.md` | Append after any project-specific conventions. |
| **Gemini Code Assist** | `GEMINI.md` | Single-file convention. |
| **Zed AI** | `.rules` | Single-file convention. |
| **Sourcegraph Cody** | `.cody/rules/vaultwares.md` | Multi-file rules. |
| **JetBrains AI Assistant** | `.idea/aiassistant/context.md` | If the project uses `.idea/`. |
| **Anthropic Skill (project-local)** | `.claude/skills/vaultwares.md` | Auto-invoked. Use the standalone `SKILL.md` instead of the managed block. |

## Wiring into `sync_submodule_rules.py`

```python
# theme-manager/tools/sync_submodule_rules.py — pseudocode

HOST_TARGETS = {
    "claude":   ["CLAUDE.md"],
    "codex":    ["AGENTS.md"],
    "cursor":   [".cursor/rules/vaultwares.mdc", ".cursorrules"],
    "windsurf": [".windsurf/rules/vaultwares.md", ".windsurfrules"],
    "copilot":  [".github/copilot-instructions.md"],
    "continue": [".continue/rules/vaultwares.md"],
    "aider":    ["CONVENTIONS.md"],
    "gemini":   ["GEMINI.md"],
    "zed":      [".rules"],
    "cody":     [".cody/rules/vaultwares.md"],
    "jb":       [".idea/aiassistant/context.md"],
}

MANAGED_START = "<!-- VAULTWARES_AGENTCIATION:MANAGED:START -->"
MANAGED_END   = "<!-- VAULTWARES_AGENTCIATION:MANAGED:END -->"

def sync_block(repo_path: Path, host: str, block: str, check_only=False):
    for filename in HOST_TARGETS[host]:
        target = repo_path / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_text(block + "\n")
            continue
        text = target.read_text()
        if MANAGED_START in text and MANAGED_END in text:
            # Replace the existing managed block.
            before = text.split(MANAGED_START)[0].rstrip() + "\n\n"
            after  = text.split(MANAGED_END)[1].lstrip()
            new_text = before + block + ("\n\n" + after if after else "\n")
        else:
            # Append.
            new_text = text.rstrip() + "\n\n" + block + "\n"
        if check_only:
            assert text == new_text, f"{target} drifted"
        else:
            target.write_text(new_text)
```

## CLI usage (current convention)

```powershell
# Check every consumer (CI / pre-commit):
python theme-manager\tools\sync_submodule_rules.py ..\<consumer-repo> --check --targets all

# Apply to one consumer:
python theme-manager\tools\sync_submodule_rules.py ..\<consumer-repo> --targets all

# Apply to a specific host only:
python theme-manager\tools\sync_submodule_rules.py ..\<consumer-repo> --targets cursor,claude
```

## Consumer repo list (current)

Maintain this list in `docs/consumer-update-roadmap.md` (Tier-3). Today:

- `vaultwares-docs`
- `vaultwares-cli`
- `vault-player`
- `vault-central`
- `vault-themes` (self)
- `vaultwares-pipelines`
- `vault-guardian`
- `vault-flows`
- `vault-explorer`
- `vaultwares-template`
- `vaultwares-v1`
- `vaultwares-identity-manager`
- `vaultwares-sentry` (private)
- `vaultwares-agentciation` (private)
- `agent-ledger` (private)
- `dispatch-wares`
- `glass-ui`
- `automation-suite`

Any new VaultWares-org repo MUST be added here within 24h of creation.

## GitHub Action (recommended next step)

Drop this in `vault-themes/.github/workflows/sync-managed-block.yml`:

```yaml
name: Sync MANAGED block to consumers
on:
  push:
    branches: [main]
    paths:
      - "AGENTS.md"
      - "brand/**"
      - "dist-to-vault-themes/sync-templates/managed-block.md"

jobs:
  fan-out:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        repo:
          - vaultwares-docs
          - vaultwares-cli
          - vault-player
          - vault-central
          # …add the full consumer list…
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with:
          repository: p-potvin/${{ matrix.repo }}
          token: ${{ secrets.SYNC_PAT }}
          path: consumer
      - run: |
          python theme-manager/tools/sync_submodule_rules.py \
            consumer --targets all
      - uses: peter-evans/create-pull-request@v6
        with:
          path: consumer
          token: ${{ secrets.SYNC_PAT }}
          branch: auto-update-vaultwares-rules
          title: "chore: sync VaultWares MANAGED block"
          body: "Auto-generated from vault-themes@${{ github.sha }}."
          commit-message: "chore: sync VaultWares MANAGED block"
```

Result: any change to the canonical files opens a PR against every consumer within a minute. Merge them (or set them to auto-merge) and every host across every repo is current.
