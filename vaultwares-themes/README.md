# vault-themes

`vault-themes` is the shared VaultWares source of truth for brand direction,
design tokens, reusable UI references, theme exports, and agent/IDE guidance.

The repo is intentionally small at the root. Start here:

| File / folder | Purpose |
| --- | --- |
| `AGENTS.md` | Canonical rules for agents, IDE assistants, style, tokens, and repo maintenance. |
| `CONTEXT.md` | Paste-ready short brief for agents and humans who need the brand context quickly. |
| `brand/` | Brand philosophy, maintainable brand guide source, bilingual strings, and tokens. |
| `assets/` | Logos, favicons, icons, and source design assets. |
| `theme-manager/` | Python tools, sync tooling, Qt/PySide exports, and generated platform exports. |
| `components/` | Reusable component references and lightweight UI examples. |
| `examples/brand-guide/` | Optional local React/Tailwind brand-guide demo. |
| `docs/` | Consumer setup, maintenance notes, migration notes, and future work. |

## Quick Checks

```powershell
python -m py_compile (Get-ChildItem -Recurse theme-manager -Filter *.py).FullName
python theme-manager\tools\sync_submodule_rules.py ..\vaultwares-website --check --targets all
cd examples\brand-guide
npm install
npm run build
=======
```
vault-themes/
├── Brand/                         # Source of truth for all brand assets
│   ├── BRAND_PHILOSOPHY.md        # Vision, mission, positioning, investor reference
│   ├── tokens.ts                  # Design token definitions (colors, type, spacing)
│   ├── tailwind.config.ts         # Tailwind config — synced with tokens.ts
│   ├── brand.i18n.ts              # Bilingual brand strings (EN / FR)
│   ├── vaultcore.ts               # VaultCore schema (Zod)
│   ├── vaultcore.validation.ts    # Extended validation rules
│   ├── vaultwares-logo.svg        # Wordmark — light backgrounds (default)
│   ├── vaultwares-logo-dark.svg   # Wordmark — dark backgrounds
│   ├── vaultwares-logo-mono.svg   # Wordmark — monochrome (embossing / print)
│   ├── vaultwares_logo_gold.jpg   # Raster reference
│   ├── minimal-logos/             # Minimal "V" logos for small spaces
│   │   ├── vaultwares-minimal-ink-filled.png  # Default (ink)
│   │   ├── vaultwares-minimal-mono-filled.png # Monochrome
│   │   └── vaultwares-minimal-gold-filled.png # Gold
│   ├── favicons/                  # Browser and system favicons
│   └── VaultWares — Brand Guide.htm  # Full visual brand guide (HTML)
├── branding/                      # Production-ready exported assets (see branding/README.md)
├── components/
│   └── glass/
│       └── LiquidGlass.tsx        # 3-D liquid glass panel (React Three Fiber)
├── BRAND_PHILOSOPHY.md            # → see Brand/BRAND_PHILOSOPHY.md
├── ROADMAP.md                     # Product & design roadmap
├── TODO.md                        # Actionable task list
├── AGENTS.md                      # AI agent rules and constraints
├── agent_manifest.md              # Registered agents and permissions
└── theme_manager.py               # Python theme token manager
```

## Brand Guide

The maintainable source is `brand/brand-guide.md`. The optional visual demo lives
in `examples/brand-guide/` and uses local assets only. The previous exported
HTML bundle was generated and has been replaced by editable source files.

## Consumer Repos

This cleanup only updates consumer repo instruction/pointer compatibility where
needed. A full style/token migration across consumers is intentionally left as
future work. See `docs/consumer-update-roadmap.md` for the repo list and next
steps.

## Rules In Short

- Privacy first, security second, functionality third.
- Do not use fear, hacker clichés, Matrix aesthetics, neon green on black, or
  jargon-heavy copy.
- Use named tokens from `brand/tokens/`; do not hardcode colors, spacing, fonts,
  radii, motion values, or glass parameters in reusable code.
- Keep English and French/Quebec French content at parity.
- Use glass UI sparingly for elevated overlays, not full pages.
=======
```ts
import '@fontsource/inter/300.css';   // weight 300 — matches Segoe UI Semilight
import '@fontsource/inter/400.css';   // weight 400 — body text
```

### 2. Import design tokens

```ts
import { colors, typography, spacing, glass } from './Brand/tokens';
```

### 3. Use bilingual brand strings

```ts
import { brandStrings } from './Brand/brand.i18n';

const locale = 'fr'; // or 'en'
const t = brandStrings[locale];

console.log(t.tagline);          // "La confidentialité d'abord…"
console.log(t.actions.continue); // "Continuer"
console.log(t.status.secured);   // "Coffre sécurisé"
```

### 4. Use the LiquidGlass component

```bash
npm install @react-three/fiber @react-three/drei three
```

```tsx
import { LiquidGlassEffect } from './components/glass/LiquidGlass'

<LiquidGlassEffect />
```

---

## Brand Principles (summary)

VaultWares is built on three principles:

1. **Privacy** — data minimization, local-first, no tracking, no telemetry
2. **Security** — open-source, auditable, correct cryptography — not theatre
3. **Functionality** — clear, fast, bilingual (EN / FR), accessible to everyone

> Full brand philosophy, competitive positioning, and visual identity rationale:
> [`Brand/BRAND_PHILOSOPHY.md`](./Brand/BRAND_PHILOSOPHY.md)

---

## Color Tokens (quick reference)

| Token | Hex | Usage |
|---|---|---|
| `vault.base` | `#002B36` | Dark theme background |
| `vault.paper` / `vault.light` | `#FDF6E3` | Light theme background |
| `vault.gold` | `#CC9B21` | Primary brand accent (V-mark) |
| `vault.cyan` | `#21B8CC` | Interactive / primary action |
| `vault.green` | `#4ECC21` | Success / secured state |
| `vault.burgundy` | `#A63D40` | Error / destructive |
| `vault.slate` | `#4A5459` | Secondary text / surfaces |
| `vault.muted` | `#586E75` | Captions / tertiary text |

---

## Logo Usage Rules

- Use `vaultwares-logo.svg` on light (`#FDF6E3`) backgrounds
- Use `vaultwares-logo-dark.svg` on dark (`#002B36`) backgrounds
- Use `vaultwares-logo-mono.svg` for single-color applications (embossing, watermarks)
- Minimum size: **32px height** (digital), **10mm** (print)
- Clear space: **½ logo height** on all sides
- Never stretch, recolor, rotate, or apply effects to the logo

---

## Minimal Logo & Favicon Usage

- Use **minimal logos** from `Brand/minimal-logos/` when the full wordmark is constrained or does not fit (e.g., UI headers, small avatars).
- **Default Variants**:
    - `-ink-filled`: Standard for light backgrounds.
    - `-mono-filled`: General purpose monochrome.
    - `-gold-filled`: High-contrast brand accent.
- **Favicons**: Use assets from `Brand/favicons/` for web browsers and application shortcuts.
- **Scaling**: Minimal logos are optimized for small sizes (e.g., 25x25px) but are provided as high-resolution sources. Always scale with smooth transformation.

---

## Contributing

- All colors must use named `vault.*` tokens — no raw hex in UI code
- All user-facing strings must have both `en` and `fr` entries in `brand.i18n.ts`
- All new/changed themes must pass WCAG AA contrast (body ≥ 4.5:1, large text ≥ 3:1)
- See `AGENTS.md` for AI agent rules

---

*© 2025 VaultWares — Built under VaultWares Enterprise Guidelines*
