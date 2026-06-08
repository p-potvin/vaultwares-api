# AGENTS.md - vault-themes

> For company-wide rules, read `vaultwares-docs/AGENTS.md` first.

This repository is the **Tier 2 Source of Truth** for brand, visual style,
theme tokens, shared UI references, and cross-AI-Assistant guidance.

## Required Reading

Before changing UI, branding, design tokens, theme exports, agent instructions,
auth UX, encrypted communication UX, or consumer propagation rules, read:

- `brand/brand-guide.md`
- `brand/philosophy.md`
- `brand/tokens/tokens.ts`
- `brand/tokens/tailwind.config.ts`
- `brand/i18n/brand.i18n.ts`
- `CONTEXT.md`
- `PQC_PROTOCOL_IMPLEMENTATION.md`

## Brand Direction

Priority order:

1. Privacy for individuals
2. Security in service of privacy
3. Functionality
4. Performance
5. Scalability
6. Developer experience

VaultWares should feel calm, precise, human, premium, and practical. Do not use fear-based security copy, hacker stereotypes, Matrix visuals, pure black/neon green palettes, vague "military-grade" claims, or jargon when plain language works.

All visible brand language should support English (code: EN) and Quebecois (code: QC). Make layouts while considering French strings may be 15-20% longer than English.

All projects must implement a dark/light theme switch (light: `codex-solar-light-revisited`, dark: `golden-slate`) situated near the EN/QC language switch, both having persistent state across sessions.

Apply these rules to any work touching `theme_manager.py`, `qt_exporter.py`,
style guides, token exports, Figma-to-code implementation, UI components, or
brand assets.

## Token Rules

- Never hardcode reusable colors, spacing, fonts, radii, motion, or glass values.
- Use named tokens from `brand/tokens/tokens.ts`.
- Keep Tailwind mapping in `brand/tokens/tailwind.config.ts`.
- Add platform exports under `theme-manager/` when another framework needs the
  same values.
- Every theme must define at least: `background`, `surface`,
  `surfaceElevated`, `textPrimary`, `textSecondary`, `accent`, `accentHover`,
  `borderSubtle`, `focusRing`, `success`, `warning`, and `danger`.

## Visual Rules

- Dark mode uses deep teal/slate, not pure black.
- Light mode uses warm paper/off-white, not stark white-only surfaces.
- Gold is the primary brand accent; cyan is the interactive accent.
- Use glass UI sparingly for elevated overlays, cards, tool panels, and command
  surfaces. Do not turn entire pages into blurred glass.
- Motion should be subtle: 120-240ms, no infinite decorative loops by default.
- Body text contrast must meet WCAG AA, 4.5:1 or better.
- Do not rely on color alone for state.

## Visual Cues & Progress Bars

All long-running or resource-intensive operations must provide explicit, real-time visual feedback to the user.

- **CLI Implementation**: Use high-fidelity progress bars. Preferred: `tqdm` (Python) and `indicatif` (Rust).
- **GUI/Web Implementation**: Use standard progress or spinner tokens defined in `theme_manager.py`. Avoid static "Loading..." text without motion.
- **Consistency**: Visual cues should follow the brand's cyan interactive accent color.

## Repo Layout

- Root: only durable entrypoints such as `AGENTS.md`, `CONTEXT.md`,
  `README.md`, `LICENSE`, `.gitignore`, and repo config.
- `brand/`: maintainable brand guide, philosophy, tokens, bilingual strings,
  and legacy notes worth preserving.
- `assets/`: logos, icons, favicons, source design assets.
- `theme-manager/`: Python managers, sync tools, validation, and platform
  exports.
- `components/`: reusable component references.
- `examples/brand-guide/`: optional lightweight demo.
- `docs/`: maintenance notes and consumer update plans.

## Agent And IDE Guidance

This file is the single canonical instruction source. Tool-specific files such
as `.github/copilot-instructions.md`, `CLAUDE.md`, Cursor rules, Windsurf rules,
Continue context, or VS Code guidance should contain only a short pointer back
to this file and `CONTEXT.md` unless the tool requires a specific wrapper.

Use `theme-manager/tools/sync_submodule_rules.py` to propagate managed guidance
blocks into consumer repositories that include `vault-themes`.

## Consumer Repo Policy

- **#1 most important:** The branding guide must be consulted before making any stylistic choices.
- **Never hardcode a color, spacing value, or font.** Always use a named token
  from `Brand/tokens.ts` or the `VaultTheme` dataclass attributes.
- Theme mode must be explicit: `light` or `dark`. Never infer it.
- Every theme must define **all** semantic color tokens listed below via the
  `VaultTheme` dataclass in `theme_manager.py`.
- Keep theme definitions centralized in `theme_manager.py`. Do not duplicate
  theme catalogs across files.
- Theme names are Title Case (user-facing). Theme IDs are kebab-case (machine).
- Every app that uses vault-themes must implement a theme picker with the 25+ themes defined in `theme_manager.py`.
- Every app must implement a dark/light switch that defaults to the user's OS (dark: `golden-slate`, light: `codex-solar-light-revisited`).
- Use the full VaultWares logo if a good place can be found without forcing it; otherwise, at the very least, use the VaultWares minimal-icon in the header.
- Implement a language switch next to the theme switch with EN/QC for English and Quebecois (the app must therefore be translated).

### VaultTheme — Full Semantic Token Reference

| Token          | Type | Role                                                   |
| -------------- | ---- | ------------------------------------------------------ |
| `name`         | str  | User-facing name (Title Case)                          |
| `mode`         | str  | `"light"` or `"dark"`                                  |
| `primary`      | hex  | Main window / root background                          |
| `surface`      | hex  | Panel / card background (slightly offset from primary) |
| `surface_alt`  | hex  | Nested element background (deepest layer)              |
| `accent`       | hex  | Brand accent — primary interactive / highlight color   |
| `accent_muted` | hex  | Desaturated or hover variant of accent                 |
| `text`         | hex  | Primary body text                                      |
| `text_muted`   | hex  | Secondary / caption / placeholder text                 |
| `text_inverse` | hex  | Text rendered on accent-colored surfaces               |
| `border`       | rgba | Subtle border for panels, inputs, separators           |
| `error`        | hex  | Semantic error / destructive state                     |
| `error_bg`     | rgba | Translucent background for error banners               |
| `warning`      | hex  | Semantic warning / caution state                       |
| `warning_bg`   | rgba | Translucent background for warning banners             |
| `success`      | hex  | Semantic success / positive state                      |
| `success_bg`   | rgba | Translucent background for success banners             |
| `info`         | hex  | Semantic informational state                           |
| `info_bg`      | rgba | Translucent background for info banners                |
| `muted`        | hex  | Muted / disabled UI elements, placeholder text         |

### Color harmony rules when adding a new theme

When choosing semantic colors for a new theme, derive them from color theory
relative to the theme's `accent`:

- **`error`**: Use a warm red / crimson that is _analogous_ (adjacent hue) to the
  accent on warm themes, or _complementary_ (opposite hue) on cool themes.
  Never use pure `#FF0000` — it looks undesigned.
- **`warning`**: Use amber / orange. It should sit between `accent` and `error`
  on the hue wheel if possible.
- **`success`**: Use a mid-saturation green or teal — the _complementary_ of a
  red or warm accent, or an _analogous_ neighbor of a cool/cyan accent.
- **`info`**: Use a calm blue or violet that does not conflict with the accent.
- **`muted`**: Desaturate and darken (dark themes) or desaturate and lighten
  (light themes) by 30–40%.
- **`*_bg` backgrounds**: Set alpha to 12–15% of the corresponding semantic color.
  This ensures readability while still conveying state.

### Base color token reference (from `Brand/tokens.ts`)

| Token              | Hex       | Role                         |
| ------------------ | --------- | ---------------------------- |
| `vault.base`       | `#002B36` | Dark background              |
| `vault.paper`      | `#FDF6E3` | Light background             |
| `vault.gold`       | `#CC9B21` | Primary brand accent         |
| `vault.gold.muted` | `#B78C1E` | Hover / pressed accent       |
| `vault.gold.light` | `#E5C06A` | Lighter accent tint          |
| `vault.cyan`       | `#21B8CC` | Interactive / primary action |
| `vault.green`      | `#4ECC21` | Success / secured state      |
| `vault.burgundy`   | `#A63D40` | Error / destructive          |
| `vault.slate`      | `#4A5459` | Secondary text / surfaces    |
| `vault.muted`      | `#586E75` | Captions / tertiary text     |

---

## Brand Asset Inventory

### Logo Variants (`Brand/`)

| File                             | Usage                                    |
| -------------------------------- | ---------------------------------------- |
| `Brand/vaultwares-logo.svg`      | Light backgrounds (default SVG)          |
| `Brand/vaultwares-logo-dark.svg` | Dark backgrounds (SVG)                   |
| `Brand/vaultwares-logo-mono.svg` | Monochrome — embossing, watermarks (SVG) |

### Minimal Icons (`Brand/minimal-logos/`)

These are **PNG exports** of the compact VaultWares mark (no wordmark), intended
for use as window icons, taskbar icons, tab favicons, and small UI spots where
the full wordmark doesn't fit.

| File                                                     | Usage                                            |
| -------------------------------------------------------- | ------------------------------------------------ |
| `Brand/minimal-logos/vaultwares-minimal-gold-filled.png` | Primary icon — dark backgrounds, window titlebar |
| `Brand/minimal-logos/vaultwares-minimal-ink-filled.png`  | Light mode icon — light backgrounds              |
| `Brand/minimal-logos/vaultwares-minimal-mono-filled.png` | Monochrome icon — single-color contexts          |
| `Brand/minimal-logos/vaultwares-minimal-mono-v2.png`     | Alternate mono — outlined/stroke variant         |
| `Brand/minimal-logos/vaultwares-minimal-mono.png`        | Legacy mono — use `v2` for new work              |

**Usage rules:**

- Desktop apps (`vault_gui.py`): use `vaultwares-minimal-gold-filled.png` for
  `setWindowIcon()` on dark themes; switch to `vaultwares-minimal-ink-filled.png`
  on light themes when possible.
- Do not scale minimal icons below 16×16px — below this size they become
  illegible. Use the full SVG wordmark at small rendered sizes instead.
- Do not apply CSS filters or colorize the PNG assets. Use the appropriate
  variant for the context.

### Production Assets (`branding/`)

Ready-to-ship assets for web, print, and packaging live in `branding/`. See
`branding/README.md` for the full inventory.

---

## Qt / PySide6 Stylesheet Rules (`qt_exporter.py`)

When generating QSS for a consuming application:

1. **All color values must come from `VaultTheme` attributes** — no inline hex
   or raw color strings inside `generate_qss()`.
2. Use the three-tier surface hierarchy:
    - `primary` → window root background
    - `surface` → panels, cards, inputs
    - `surface_alt` → nested inputs, dropdown popups, pressed states
3. Expose semantic frame `objectName` IDs for status banners:
    - `ErrorBanner`, `WarningBanner`, `SuccessBanner`, `InfoBanner`
4. Color-code log/monitor text inline using `theme.<semantic_token>` values —
   never hardcode error/warning/success colors in application logic.
5. For the `QProgressBar`, always set `setTextVisible(True)` and connect
   `setValue()` to the worker's `progress_percent` signal.
6. Scrollbars must be styled to use `border` and `accent_muted` so they remain
   consistent across all themes.

Submodule-local instructions do not automatically govern parent repos. Consumer
repos need their own managed pointers that tell agents and IDEs to read this
repo before UI, branding, token, theme, auth UX, encrypted communication UX, or
Figma-derived implementation work.

This cleanup only updates compatibility pointers. A full consumer repo
style/token migration is future work and is tracked in
`docs/consumer-update-roadmap.md`.

## Python And Tooling

- Body text contrast: **WCAG AA ≥ 4.5:1** — required on every component.
- Large text / UI elements: **WCAG AA large ≥ 3.0:1** — required.
- New or changed themes must pass a contrast check against the `text` /
  `text_inverse` foreground values before merging.
- Bilingual strings must be tested at the same layout breakpoints — FR is longer.

Python files belong under `theme-manager/`. Keep them dependency-light and
cross-platform. When moving tools, keep import paths working and run:

```powershell
python -m py_compile (Get-ChildItem -Recurse theme-manager -Filter *.py).FullName
```

## Brand Guide Demo

The editable guide source is `brand/brand-guide.md`. The optional visual demo is
under `examples/brand-guide/`. The demo must:

Security-related UX must follow these rules:

- Authentication and encrypted client-to-client communication flows must be
  designed around **post-quantum cryptography with ML-KEM** as the
  key-encapsulation mechanism.
- **Never** design a flow where the server can read, persist, derive, or
  reconstruct private keys or shared decryption keys used between two clients.
- Security-related UI must preserve the VaultWares privacy-first posture.

- Use local assets only.
- Avoid external network requests.
- Stay isolated from consumer runtime dependencies.
- Build successfully before completion when touched.

## Completion Checklist

- Updated paths in `README.md`, `CONTEXT.md`, and relevant docs.
- No duplicate canonical instruction files.
- No generated caches or build bundles committed unless intentionally needed.
- Python tools compile.
- Brand guide demo builds when touched.
  -## Mandatory: Agent Ledger

Record all completed work in the shared agent ledger as the last step before replying.

## Persistent Knowledge & Scout Reports

To optimize credit usage while ensuring assistants don't miss "expensive" info, we maintain a shared ledger of technical discoveries.

> [!IMPORTANT]
> **Scout Consulting Parameters**: Assistants MUST ONLY consult `vaultwares-docs/KNOWLEDGE_SCOUT.md` under these conditions:
>
> 1. **Session Initialization**: Once per new Conversation ID, during the first research step.
> 2. **Canonical Failure**: If a search for a file mentioned in the SoT Hierarchy fails.
> 3. **High-Value Context**: If the prompt contains keywords: `VPS`, `SSH`, `HSM`, `deployment`, `credential`, or `submodule`.

## Design & Brand → vault-themes

### Required flow (do not skip steps)

1. Run `get_design_context` on the exact node(s) to implement.
2. Run `get_screenshot` for visual parity checks.
3. Map all Figma color values to `VaultTheme` token references before writing code.
4. Reuse existing components from `components/` first; only create new ones when
   reuse is not possible.
5. Validate final UI for both visual parity and WCAG AA contrast compliance.

### Implementation rules

- Treat Figma-generated code as a structural draft — never final style output.
- Replace all raw hex / pixel values with token references.
- Use an 8px spacing base scale unless the host project enforces a stricter scale.
- Prefer subtle motion. Avoid continuous animations — they distract and degrade
  performance on low-end hardware.

---

## Quality Gates

Before marking any task complete:

- [ ] All colors reference `VaultTheme.<token>` — no raw hex strings
- [ ] All strings exist in `Brand/brand.i18n.ts` in both EN and FR
- [ ] All 19 `VaultTheme` tokens are defined for any new theme added
- [ ] Semantic `*_bg` backgrounds use 12–15% alpha rgba values
- [ ] WCAG AA contrast passes for all text and interactive elements
- [ ] Logo/icon used matches the theme mode (gold-filled → dark; ink-filled → light)
- [ ] No neon green on black, no "hacker" visual clichés
- [ ] If a new theme was added: contrast check against white and black passes
- [ ] Any fallback behavior is deterministic and documented

If a rule here conflicts with a host application's stricter style or
accessibility policy, **the stricter policy wins.**
