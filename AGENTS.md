# vaultwares-pipelines

> For company-wide rules, read `vaultwares-docs/AGENTS.md` first.

<!-- VAULT-THEMES-SUBMODULE:START -->
## vaultwares-themes Submodule

Before UI, branding, or token work, read:

- `vaultwares-themes/AGENTS.md`
- `vaultwares-themes/CONTEXT.md`
<!-- VAULT-THEMES-SUBMODULE:END -->

## VaultWares Repo Instructions

### Editing rule

When working in the `vaultwares` repository, you can edit files as needed for your task. However, do not make any Git commits or push changes on the `main` branch unless you explicitly asked for that in the current turn.

### Standalone Repository Rule

When a task involves `vaultwares-themes`, `vaultwares-adk`, or `vaultwares-adk`, make the real change in the standalone repository itself.
If you encounter a nested copy or submodule mirror here, use it as context only and do not treat it as the authoritative source for the change.

### Practical intent

The goal of the rule is to prevent accidental edits in the wrong checkout, not to discourage local file changes.
Edit the right file in the right repo, verify it, and stop before committing on `main` unless explicitly requested.
