from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

START_MARKER = "<!-- VAULT-THEMES-SUBMODULE:START -->"
END_MARKER = "<!-- VAULT-THEMES-SUBMODULE:END -->"

BASE_BLOCK = """<!-- VAULT-THEMES-SUBMODULE:START -->
## Vault Themes Submodule Rules

This repository includes `vault-themes`. Before changing UI, branding, design
systems, theme tokens, shared components, authentication UX, encrypted
client-to-client communication UX, Figma-derived implementation, or agent/IDE
instructions, read these stable root files:

- `vault-themes/AGENTS.md`
- `vault-themes/CONTEXT.md`

When the submodule has the cleaned layout, also read:

- `vault-themes/brand/brand-guide.md`
- `vault-themes/brand/tokens/tokens.ts`

Treat `vault-themes` as the shared VaultWares source of truth. Do not copy its
rules into this repo unless a tool-specific file requires a short pointer.
<!-- VAULT-THEMES-SUBMODULE:END -->
"""

CURSOR_HEADER = """---
description: Require VaultWares submodule guidance before UI, branding, design-system, auth UX, encrypted communication UX, or Figma-derived work.
globs: "**/*"
alwaysApply: false
---
"""

CURSOR_BLOCK = """
<!-- VAULT-THEMES-SUBMODULE:START -->
Read `vault-themes/AGENTS.md` and `vault-themes/CONTEXT.md` before covered
VaultWares work. When present, also read `vault-themes/brand/brand-guide.md`
and `vault-themes/brand/tokens/tokens.ts`.
<!-- VAULT-THEMES-SUBMODULE:END -->
"""

SHORT_BLOCK = """<!-- VAULT-THEMES-SUBMODULE:START -->
VaultWares guidance lives in `vault-themes/AGENTS.md` and `vault-themes/CONTEXT.md`.
Read those files before UI, branding, design-system, token, auth UX, encrypted
communication UX, Figma-derived, or agent-instruction work.
<!-- VAULT-THEMES-SUBMODULE:END -->
"""


@dataclass(frozen=True)
class Target:
    name: str
    relative_path: Path
    block: str
    empty_prefix: str = ""


TARGETS = {
    "codex": Target("codex", Path("AGENTS.md"), BASE_BLOCK),
    "claude": Target("claude", Path("CLAUDE.md"), BASE_BLOCK),
    "copilot": Target("copilot", Path(".github/copilot-instructions.md"), SHORT_BLOCK),
    "cursor": Target("cursor", Path(".cursor/rules/vault-themes-submodule.mdc"), CURSOR_BLOCK, CURSOR_HEADER),
    "cursorrules": Target("cursorrules", Path(".cursorrules"), SHORT_BLOCK),
    "windsurf": Target("windsurf", Path(".windsurfrules"), SHORT_BLOCK),
    "continue": Target("continue", Path(".continue/context.md"), SHORT_BLOCK),
    "vscode": Target("vscode", Path(".vscode/vault-themes.instructions.md"), SHORT_BLOCK),
    "cli": Target("cli", Path("CONTEXT.md"), BASE_BLOCK),
    "tui": Target("tui", Path("TUI_AGENTS.md"), SHORT_BLOCK),
}


def replace_or_append(existing: str, block: str) -> str:
    if START_MARKER in existing and END_MARKER in existing:
        start = existing.index(START_MARKER)
        end = existing.index(END_MARKER) + len(END_MARKER)
        return (existing[:start] + block.strip() + existing[end:]).rstrip() + "\n"

    if not existing.strip():
        return block.strip() + "\n"

    return existing.rstrip() + "\n\n" + block.strip() + "\n"


def resolve_targets(names: Iterable[str]) -> list[Target]:
    selected = list(names)
    if not selected or "all" in selected:
        selected = list(TARGETS)

    unknown = [name for name in selected if name not in TARGETS]
    if unknown:
        allowed = ", ".join(["all", *sorted(TARGETS)])
        raise SystemExit(f"Unknown target(s): {', '.join(unknown)}. Allowed: {allowed}")

    deduped: list[Target] = []
    seen_paths: set[Path] = set()
    for name in selected:
        target = TARGETS[name]
        if target.relative_path not in seen_paths:
            deduped.append(target)
            seen_paths.add(target.relative_path)
    return deduped


def ensure_consumer_root(consumer_root: Path, submodule_path: str) -> None:
    if not consumer_root.exists():
        raise SystemExit(f"Consumer root does not exist: {consumer_root}")

    vault_themes = consumer_root / submodule_path
    if not vault_themes.exists():
        raise SystemExit(
            f"Consumer repo does not appear to contain a vault-themes submodule: {vault_themes}"
        )


def sync_target(consumer_root: Path, target: Target, *, check: bool, dry_run: bool) -> bool:
    path = consumer_root / target.relative_path
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    seed = existing
    if not seed.strip() and target.empty_prefix:
        seed = target.empty_prefix.rstrip() + "\n\n"

    updated = replace_or_append(seed, target.block)

    changed = existing != updated
    if check:
        status = "ok" if not changed else "needs update"
        print(f"{status}: {path}")
        return changed

    if dry_run:
        action = "would update" if changed else "unchanged"
        print(f"{action}: {path}")
        return changed

    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        print(f"updated: {path}")
    else:
        print(f"unchanged: {path}")

    return changed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync vault-themes submodule guidance into consumer repo agent and IDE files."
    )
    parser.add_argument("consumer_root", help="Absolute or relative path to the consumer repository root.")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["codex", "claude", "copilot", "cursor"],
        help="Targets to sync. Use 'all' for every supported surface.",
    )
    parser.add_argument(
        "--submodule-path",
        default="vault-themes",
        help="Path to the vault-themes submodule relative to the consumer root.",
    )
    parser.add_argument("--check", action="store_true", help="Report whether files need updates and exit non-zero if they do.")
    parser.add_argument("--dry-run", action="store_true", help="Show planned updates without writing files.")
    parser.add_argument("--write", action="store_true", help="Write updates. This is the default unless --check or --dry-run is set.")
    args = parser.parse_args()

    consumer_root = Path(args.consumer_root).resolve()
    ensure_consumer_root(consumer_root, args.submodule_path)

    targets = resolve_targets(args.targets)
    changed = False
    for target in targets:
        changed = sync_target(consumer_root, target, check=args.check, dry_run=args.dry_run) or changed

    return 1 if args.check and changed else 0


if __name__ == "__main__":
    raise SystemExit(main())
