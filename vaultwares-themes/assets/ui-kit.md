# VaultWares UI Kit — Source of Truth

> **Last updated:** May 17, 2026 · **Version:** 0.1
> **Canonical location:** `vault-themes/brand/ui-kit.md`
> **Companion files:** [`brand-guide.md`](./brand-guide.md) · [`philosophy.md`](./philosophy.md) · [`tokens/tokens.ts`](./tokens/tokens.ts) · [`../AGENTS.md`](../AGENTS.md)

This file is the canonical reference for **building VaultWares product UI** — desktop apps (Electron, PySide6, WinUI3), web SPAs, internal tools. It is read by every AI host operating on a VaultWares repository before any UI change.

If anything in this file conflicts with a host repo's stricter accessibility, security, or platform policy — **the stricter policy wins.**

---

## 1. What this is (and isn't)

| This document defines | This document does NOT define |
| --- | --- |
| Component vocabulary, voice, motion, density, portability | Marketing pages, blog posts, docs.vaultwares.com (those live in `vaultwares-docs`) |
| The instrument-grade UI for products (VaultMonitor admin, VaultCrypt client, etc.) | One-off internal scripts or developer-only CLIs |
| Token usage rules for any framework | Hex values themselves — those live in `tokens/tokens.ts` |
| The EN ⇄ FR bilingual contract for visible strings | Translations themselves — those live in `i18n/brand.i18n.ts` |

---

## 2. The vocabulary shift — read first

VaultWares products are **professional instruments**, not websites. The component vocabulary is closer to 1Password 8, Tailscale, Linear's app shell, shadcn, and Sourcegraph than to any marketing-flavored design system. This is the single most important framing — most AI hosts default to web-flavored components and need to be redirected.

| Default web vocabulary (avoid) | VaultWares vocabulary (use) |
| --- | --- |
| Hero cards · marketing CTAs | App shell with title bar + sidebar + content + status bar |
| Card-grid layouts | Lists with hairline dividers, hover-reveal row actions |
| Big modal dialogs | Right-rail drawers · inline edit · command palette |
| Form sections with H2 headings | Property inspectors (label-above-control, tight) |
| Bubble-pill status badges | 6 px colored dot + label, no chrome |
| Page-level breadcrumbs | Tabstrip embedded in the title bar |
| Pages of text | Dense lists with monospace metadata |
| Full-bleed marketing hero | Two paper tones layered, depth from value not blur |
| Toast over a hero panel | Corner-docked toasts + status-bar messages |

If a request looks like a website, *first* confirm it's actually a website (marketing surface) and not a product UI. Default assumption: it's a product UI.

---

## 3. Tokens (compact reference)

Source of truth: [`tokens/tokens.ts`](./tokens/tokens.ts). Never hardcode hex, spacing, font, radius, motion, or glass values in reusable code.

### Color

| Token | Hex | Role |
| --- | --- | --- |
| `vault.base` | `#002B36` | Dark surface — deep teal (NOT black) |
| `vault.paper` | `#FDF6E3` | Light surface — warm paper (NOT white) |
| `vault.paperBright` | `#FDFCF7` | Elevated light surface |
| `vault.ink` | `#002B36` | Primary text on paper |
| `vault.slate` | `#4A5459` | Secondary text / surface |
| `vault.muted` | `#586E75` | Captions / metadata |
| `vault.deepSea` | `#0A2540` | Alt enterprise navy |
| `vault.gold` | `#CC9B21` | **Primary brand accent** — V mark, primary actions, brand surfaces only |
| `vault.gold.muted` | `#B78C1E` | Gold hover/pressed |
| `vault.gold.light` | `#E5C06A` | Gold tint, dark-mode accent |
| `vault.cyan` | `#21B8CC` | **Interaction signal** — focus, links, primary control radios |
| `vault.green` | `#4ECC21` | Secured / success / "live" toggles |
| `vault.burgundy` | `#A63D40` | Error / destructive |

**Inviolable rules.** Gold = brand. Cyan = interaction. Green = secured/live. Burgundy = destructive. They never swap roles. Translucent semantic backgrounds use 12–15% alpha of the corresponding semantic color.

### Typography

```
sans: "Segoe UI Semilight", "Segoe UI", "Inter", system-ui, sans-serif   (weight 300)
mono: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace
```

Inter 300 is the cross-platform fallback for Segoe UI Semilight (not redistributable). Light weight is intentional — VaultWares does not shout.

### Spacing · radii · motion

- **Spacing** (8 px base): `4 8 12 16 20 24 32 40 48 64 80 96`.
- **Radii**: `4 8 12 16 20` · pill `999`. Buttons/inputs → 7–8 px. Cards → 10–12 px. Overlays → 12 px. Pills → 999.
- **Motion**: `120ms` (taps) · `180ms` (state) · `240ms` (entry/exit). Easing: `cubic-bezier(0.2, 0.8, 0.2, 1)` for entries, `cubic-bezier(0.4, 0, 0.2, 1)` for state. **No infinite decorative loops.**
- **Borders**: 1 px hairlines. `rgba(0,43,54,0.14)` on paper, `rgba(253,246,227,0.18)` on dark. 2 px reserved for focused/selected.

### Glass (sparingly)

Glass is a *supporting* effect, not the identity. **Never full-page blur.** Three levels: `8 / 16 / 20 px`. **In product UI we default to NO glass** — the paper-on-paper layering carries depth. Glass is reserved for command palettes and the rare focused overlay.

---

## 4. Voice rules

Calm · precise · human · principled · competent. Closer to a premium notebook than a threat-intelligence dashboard.

### Hard rules

- Second person, active voice. Sentence case.
- Bilingual parity EN ↔ Quebec FR for every visible string. Layouts tolerate FR being **15–20% longer**.
- Date format: `April 24, 2026` (EN) · `24 avril 2026` (FR).
- Quebec French — *courriel* (not *email*), *fichier* (not *file*), *téléverser* (not *uploader*).
- No emoji in product UI, marketing, or docs.
- No unicode glyphs as UI icons (no `→`, no `✓`). Use Lucide.
- Name the algorithm or certification when relevant ("AES-256-XTS", "FIPS 140-3 Level 3", "ML-KEM-1024").
- Honest scope: "tamper-evident", not "tamper-proof". "Encrypted at rest", not "uncrackable".

### Forbidden / replacements

| Forbidden | Use instead |
| --- | --- |
| "just", "simply", "easy" (unless factually proven) | Describe the steps. |
| "military-grade" / "fortress-grade" | Name the algorithm, or just *"Vault secured."* |
| "hacker-proof" / "bulletproof" | Honest scope: "Tamper-evident", "Verified by FIPS 140-3 L3" |
| "CRITICAL SECURITY WARNING" | *"We noticed something. Here's what to do."* |
| "Proceed" | *"Continue."* |
| "We collect this for your security." | *"This is optional and off by default."* |
| Competitor product names | — |

### Anchors

- Tagline: *"Privacy first. Security in service."* / *"La confidentialité d'abord. La sécurité au service."*
- Promise: *"Your data. Your device. Your rules."* / *"Vos données. Vos appareils. Vos règles."*

---

## 5. Component inventory

Every primitive in the kit ships with the same posture: 30 px control height, hairline borders, paper-on-paper depth, mono metadata where appropriate. Sources: `vault-themes/components/` (when present) or the reference implementation in the design environment.

| Component | Shape | Notes |
| --- | --- | --- |
| **Button** | 30 px height · 7 px radius · 13 px text | Variants: `primary` (gold, paper text), `secondary` (paper-bright, hairline), `ghost` (transparent), `danger` (burgundy text + border). Sizes `sm` 26 / `md` 30 / `lg` 34. Keyboard hints (`Kbd`) live *inside* the button. |
| **IconButton** | 28 px square · ghost by default | Always carries an `aria-label`. |
| **Input** | 32 px height · 7 px radius · cyan focus (3 px halo @ 22% alpha) | `.mono` variant for IDs, paths, fingerprints. Error → burgundy border + soft burgundy halo. |
| **PasswordInput** | Input + eye toggle | Toggle is icon-only, 22 px. |
| **SearchInput** | Input + leading search icon + trailing `Kbd` | Default kbd hint: `⌘K`. |
| **Select** | 32 px · inline-SVG chevron · 10 px right padding | `appearance: none` cross-browser. Cursor `pointer`. |
| **Textarea** | Auto-height · min 80 px · resize vertical | |
| **Toggle** | 32 × 18 pill · GREEN when ON | Off state is `rgba(0,43,54,0.18)`. Hover deepens. |
| **Checkbox** | 16 px · GOLD when ON | Brand action — gold reads as "I'm asserting this." |
| **Radio** | 16 px · CYAN when ON | Interaction — cyan reads as "I picked this." |
| **Status** | 6 px dot + label | Tones: `secured` (green) · `update` (gold) · `idle` (muted) · `locked` (burgundy) · `offline` (faint). `pulse` for live states only. |
| **Badge** | 18 px height · mono · 10 px · uppercase | Tones: `default` `outline` `fips` (deep-sea + gold) `gold` (filled) `success` `warning` `danger` `info`. |
| **Tag** | 20 px pill · removable `x` | Lower density than Badge. Use for free-form labels. |
| **Avatar** | 26 px circle · seeded color · monogram | Color deterministic from name hash. |
| **CodeChip** | 22 px mono inline · copy button | For secrets, paths, fingerprints in body copy. |
| **Card** | Hairline border · 10–12 px radius · **NO shadow** · optional mono strip on top | Variants: product / status / metric (large number + sparkline). |
| **Banner** | 3 px tone-colored left edge · square left corners | Tones: `success` `warning` `danger` `info`. Solid background, hairline border. |
| **Toast** | Corner-docked bottom-right · solid · 240 ms entry · no infinite motion | Dismissible. Stack vertically. |
| **Dialog** | Solid paper-bright · 12 px radius · 0.99 → 1.0 scale entry · Esc-dismissable | Footer pinned to the right with primary action last. |
| **Drawer** | Right-side · 400 px · 240 ms slide · solid background · soft scrim | Same footer pattern as Dialog. |
| **Bi (Bilingual)** | `<Bi en="…" fr="…" />` | Renders both inline (FR muted) by default; renders one when inside `<LangCtx.Provider value="…">`. The mechanism IS the EN/FR app-level toggle. |
| **Kbd** | 18 px chip · mono 10 px · 1.5 px bottom border | Visible everywhere keyboard shortcuts exist. |

### Shell pieces

| Region | Treatment |
| --- | --- |
| **Title bar** (44 px) | Workspace pill (left) · tabstrip (center) · search + EN/FR + avatar (right). Drag region everywhere except the controls. |
| **Sidebar** (248 px) | Section headers (uppercase, 10.5 px), items 13.5 px with 15 px icons. Active item: paper-bright background + 2 px gold left edge. |
| **Data list** | Sticky 32 px head row with uppercase 10.5 px column labels. 40 px rows with hairline dividers. Hover background → paper-bright. Selected → paper-bright + 2 px gold left edge. Overflow menu reveals on hover. |
| **Right rail** (320 px) | Header (icon + name + ID + status + tags) · tab strip · property list (uppercase label / value) · pinned footer of actions. |
| **Status bar** (28 px) | Mono 11 px. Left: connection state. Center: encryption stack (e.g. *"AES-256-XTS · TLS 1.3 · ML-KEM-1024"*). Right: sync time + env pill. |

---

## 6. Platform portability — the discipline

Every visual choice ports cleanly to PySide6 (QSS) and WinUI3 (XAML). This is a *design constraint*, not a workaround. If you can't render an effect with a solid fill, 1 px border, or simple shape, it doesn't belong in the kit.

| Effect | React/CSS | PySide6 / QSS | WinUI3 / XAML |
| --- | --- | --- | --- |
| Hairline border | `border: 1px solid rgba(0,43,54,.14)` | `border: 1px solid rgba(0,43,54,36)` | `<Border BorderThickness="1" BorderBrush="{StaticResource vault-border}"/>` |
| Paper-on-paper depth | `background: var(--vault-paper-bright)` on inner | nested `QFrame` with different `background-color` | nested `Border` with different `Background` |
| Status dot | `border-radius: 50%` + `box-shadow` halo | `QLabel` w/ `border-radius: 3px` | `<Ellipse>` + outer `<Ellipse Opacity="0.18"/>` |
| Focus ring (3 px cyan halo) | `box-shadow: 0 0 0 3px rgba(33,184,204,.22)` | `:focus { outline: 3px solid rgba(33,184,204,56); }` via stylesheet | `FocusVisualPrimaryThickness="3"` + Cyan brush |
| Toggle slide | `transform: translateX(14px)` w/ 180 ms ease | `QPropertyAnimation` on geometry | `Storyboard` with `TranslateTransform` |
| Toast entry | `@keyframes` opacity + translateY | `QPropertyAnimation` on pos+opacity | `Storyboard` |
| Selected-row 2 px gold edge | `::before` with 2 px width | inner `QFrame` with `border-left: 2px solid` | `<Border BorderThickness="2,0,0,0"/>` |

**Forbidden across all platforms** (because they don't port consistently):
`backdrop-filter`, full-page blur, multi-stop gradients, complex SVG-only effects, animated icons, infinite decorative motion loops.

---

## 7. Bilingual contract

Two layers:

1. **Strings.** Every visible string lives in [`i18n/brand.i18n.ts`](./i18n/brand.i18n.ts) as `{ en, fr }`. A new string is never landed in only one language.
2. **Layout.** FR runs +15–20% longer. Use `flex-wrap`, `min-content`, or `clamp()` widths. Never set a fixed width on a label or button.

The `<Bi en="…" fr="…" />` component is the kit-level shorthand. In a host app the *real* binding is `t.actions.continue` against the i18n table, but `<Bi>` matches the same contract and is acceptable for prototypes and brief surfaces.

---

## 8. Iconography

Lucide is the default. 1.5–2 px stroke, rounded joins, never filled (except the brand mark). The icon ships as plain inline SVG so every framework can render it without a dependency.

| Use case | Lucide name |
| --- | --- |
| Brand mark in titlebars / dock | (use `vaultwares-minimal-{gold,ink,mono}-filled.png` — this is **brand**, not a UI icon) |
| Secured / vault | `shield-check` |
| Lock / encrypt | `lock` |
| Key / rotate | `key` / `rotate-cw` |
| Hardware storage | `hard-drive` |
| HSM | `cpu` |
| Biometric | `scan` / `fingerprint` |
| Server / appliance | `server` |
| Settings | `settings` (cog) |
| Search | `search` |
| Languages toggle | `languages` |
| Command palette | `command` |

When `docs.json` references a FontAwesome name (`shield-halved`, `microchip`, `usb-drive`), substitute the closest Lucide equivalent for visual consistency.

**Never:** emoji as icons. Unicode glyphs as icons. Original SVG drawings (ask first if Lucide lacks something).

---

## 9. Anti-patterns

The fastest way to spot a non-VaultWares UI is by what it shouldn't be. If an output has any of these, reject and redo:

- Pure black background, neon green text, Matrix rain, padlock-with-lightning illustrations.
- Full-page or large-panel `backdrop-filter: blur(…)`.
- Multi-stop rainbow gradients. Gradients that span the viewport.
- "Just", "simply", "easy", "military-grade", "hacker-proof", "fortress-grade", "Proceed", "CRITICAL".
- Emoji as UI elements. Unicode arrows or check marks as UI icons.
- Cards with a gradient background, left-border accent stripe, or emoji-as-icon.
- Status bubbles with full-pill backgrounds and a tiny icon.
- Infinite decorative animation loops on buttons, cards, or accent strips.
- Hardcoded hex values in reusable code (always use a `vault.*` token).
- A user-facing string in EN without an FR counterpart.
- Stock photo of a person pointing at a screen, code-rain, or padlock illustrations.

---

## 10. Quality gates — checklist before merge

- [ ] All colors reference a `vault.*` token. No raw hex outside `tokens.ts`.
- [ ] Every visible string exists in both `en` and `fr` in `brand.i18n.ts`.
- [ ] FR layout has been visually verified at the same breakpoints as EN.
- [ ] Body contrast ≥ 4.5:1 (WCAG AA). Large text / UI ≥ 3.0:1.
- [ ] Focus ring is visible in both light and dark themes.
- [ ] No reliance on color alone for state (icon + label always pair).
- [ ] No emoji in product/UI/marketing copy.
- [ ] No `backdrop-filter` on full-page or large-panel surfaces.
- [ ] Logo variant matches mode (gold-filled on dark, ink-filled on light, mono in single-color contexts).
- [ ] If a primitive was added: it has a QSS and XAML port note in this file.

---

## 11. Required reading order

For any AI host opening a VaultWares repo for the first time:

1. [`../AGENTS.md`](../AGENTS.md) — top rules, security posture, theme tokens.
2. This file (`brand/ui-kit.md`) — product-UI vocabulary.
3. [`brand-guide.md`](./brand-guide.md) — voice + brand foundation.
4. [`philosophy.md`](./philosophy.md) — *why* we make these choices (optional but useful).
5. [`tokens/tokens.ts`](./tokens/tokens.ts) — the live values.
6. [`i18n/brand.i18n.ts`](./i18n/brand.i18n.ts) — the canonical strings.

For UI work specifically: 1 → 2 → 5 → 6 is the minimum.

---

## 12. Updating this file

1. Edit `brand/ui-kit.md` here (canonical).
2. Update `tokens/tokens.ts` if visual values change.
3. Update `i18n/brand.i18n.ts` if visible strings change.
4. Run `theme-manager/tools/sync_submodule_rules.py --targets all` to propagate the managed block into every consumer repo's host-specific files.
5. Open the auto-generated PR(s) and merge.

*© VaultWares — Built under VaultWares Enterprise Guidelines*
