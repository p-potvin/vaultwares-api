# Deploying this to vault-themes

These artifacts are ready to lift into [`p-potvin/vault-themes`](https://github.com/p-potvin/vault-themes). They replace nothing existing; they are net-new additions to a repo you already maintain.

## What's in this folder

```
dist-to-vault-themes/
├── README.md                              ← you are here
├── brand/
│   └── ui-kit.md                          ← NEW canonical doc for the UI kit
└── sync-templates/
    ├── managed-block.md                   ← the body of the MANAGED block
    ├── host-targets.md                    ← per-host file map + sync-tool wiring
    └── example-CLAUDE.md                  ← a consumer repo's CLAUDE.md, annotated
```

## Drop-in plan

### Step 1 — Add the canonical doc (1 minute)

```bash
cp dist-to-vault-themes/brand/ui-kit.md \
   ../vault-themes/brand/ui-kit.md
cd ../vault-themes
git add brand/ui-kit.md
git commit -m "docs(brand): add UI kit source of truth"
```

This file is the missing canonical reference for the product-UI vocabulary (the instrument-not-website framing, the component inventory, the QSS/XAML port notes, the quality gates). It's intentionally written for AI hosts and humans to read end-to-end.

### Step 2 — Wire the MANAGED block (5 minutes)

Open `theme-manager/tools/sync_submodule_rules.py` and:

1. **Replace the block payload.** Use the content from `sync-templates/managed-block.md` as the new value of whatever variable holds the block (likely `MANAGED_BLOCK_TEXT` or similar).
2. **Extend host targets.** Use the `HOST_TARGETS` dict from `sync-templates/host-targets.md` as the source of truth. The previous tool likely only handled `CLAUDE.md` + maybe `AGENTS.md`. Add the rest (Cursor, Windsurf, Copilot, Continue, Aider, Gemini, Zed, Cody, JetBrains).
3. **Add `--targets` CLI flag.** Comma-separated list of host keys, or `all` (default).
4. **Add `--check` mode.** Fails if any file has drifted from the expected block — for CI use.

The wiring code is sketched in `sync-templates/host-targets.md`.

### Step 3 — Propagate across consumers (1 command per repo, or one Action)

**Manual.** For each consumer in the list:

```powershell
python theme-manager\tools\sync_submodule_rules.py ..\<consumer> --targets all
cd ..\<consumer>
git checkout -b chore/vw-rules
git add -A && git commit -m "chore: sync VaultWares MANAGED block"
git push -u origin chore/vw-rules
gh pr create --fill --base main
```

**Automated.** Drop the GitHub Action from `sync-templates/host-targets.md` into `vault-themes/.github/workflows/`. Then any push to `vault-themes/main` opens a PR against every consumer within a minute.

### Step 4 — Verify

For one consumer, confirm the block appears in:

- `CLAUDE.md`
- `AGENTS.md`
- `.cursor/rules/vaultwares.mdc`
- `.windsurf/rules/vaultwares.md`
- `.github/copilot-instructions.md`
- `.continue/rules/vaultwares.md`
- `CONVENTIONS.md`
- `GEMINI.md`
- `.rules`
- `.cody/rules/vaultwares.md`

Open a fresh chat in each host. Ask: *"What's the primary brand color?"* The answer should be **gold `#CC9B21`** — not Tailwind blue.

## Two design choices worth flagging

### 1. Pointer vs full content

The managed block is intentionally **pointer-only** (~50 lines) — it lists the canonical files, the non-negotiables, the color quick-ref, and the anti-patterns. It does NOT duplicate the full UI kit doc. Reason: the more content lives in the block, the more it drifts. Anything an agent needs the full detail on, it should read from `vault-themes/brand/ui-kit.md` directly.

If a consumer doesn't have `vault-themes` as a submodule, the block instructs the agent to fetch it before proceeding. This is the *correct* failure mode — better to pause than to act on stale info.

### 2. MCP as the future state

Once the markdown layer is stable, the next move is an `vaultwares-design-system` MCP server (you have `VaultWares/fastmcp` already). The server reads the same `tokens.ts` and `brand.i18n.ts` files; it exposes:

- `get_tokens(format: ts|css|qss|xaml)` — live token map
- `get_voice_rules()` — forbidden phrases + replacements
- `get_component(name, target: react|qss|xaml)` — primitive source
- `check_copy(text)` — lint a string for "military-grade", "Proceed", emoji
- `lint_color(hex)` — confirm membership in the token set

MCP-capable hosts (Claude Desktop, Claude Code, Cursor + MCP, Windsurf + MCP, your `vaultwares-cli`) get **executable** rules. Non-MCP hosts keep the markdown. Both layers stay in sync because they read the same files. This is a v0.2 / v0.3 effort — not blocking.

## What's NOT in this folder

- A new `tokens.ts` — yours is already canonical, nothing to change.
- A new `brand-guide.md` — yours is already canonical, nothing to change.
- A new `philosophy.md` — yours is already canonical, nothing to change.
- A new `AGENTS.md` — yours is already canonical, this just adds `ui-kit.md` to its required-reading list (a 1-line patch).

## One-line patch to vault-themes/AGENTS.md

In the "Required Reading" section of `vault-themes/AGENTS.md`, add this line:

```markdown
- `brand/ui-kit.md`
```

Right after `brand/brand-guide.md`. That's the only change to existing files.
