# VaultWares Design System

> **Privacy first. Security in service.**
> A design system for VaultWares — enterprise-grade security hardware and software, built 100% from Free Open-Source Software & Hardware.

This project is the working source of truth for the VaultWares brand inside this design environment. It collects the real tokens, logos, and components that ship with VaultWares products — adapted for HTML/CSS prototyping and slide work.

---

## Sources

The system was assembled from the following materials. All paths below are read-only references — copies of the assets we use are stored locally in `assets/`.

| Source | Path / URL | What we used |
| --- | --- | --- |
| **vault-themes** repo (Tier-2 source of truth) | [`p-potvin/vault-themes`](https://github.com/p-potvin/vault-themes) — branch `main` | `brand/tokens/tokens.ts`, `brand/tokens/css-variables.css`, `brand/brand-guide.md`, `brand/philosophy.md`, `examples/brand-guide/` |
| **vaultwares-docs** repo (Mintlify docs) | [`p-potvin/vaultwares-docs`](https://github.com/p-potvin/vaultwares-docs) — branch `main` | `docs.json`, `index.mdx`, `quickstart.mdx`, `branding.mdx`, `logo/{light,dark}.svg`, `favicon.svg`, `CLAUDE.md` |
| **Brand guidelines** (pasted) | `branding.mdx` — Last updated April 24, 2026 · v1.0 | Tagline, forbidden language, primary/accent colors, font stack |
| **Local asset folder** (mounted, read-only) | `assets/{logos,favicons,icons,source}` | Wordmark + minimal-V PNG/SVG variants, favicon set |
| **Uploaded files** | `uploads/vaultwares-*` | Same logo set, plus `vaultwares-react-logo.jsx` placeholder |

> Tokens here intentionally follow `vault-themes/brand/tokens/tokens.ts` rather than the `docs.json` Mintlify theme (which uses a default Tailwind-blue `#1E40AF` set). The brand-guide repo is the canonical source.

---

## What VaultWares makes

A privacy-first cybersecurity company shipping hardware and software products built entirely from FOSS components. Bilingual EN/FR (Quebec French) as a product requirement, not an afterthought. Primary markets: Canada, France, EU.

**Hardware** — VaultDrive (encrypted USB storage), VaultHSM (hardware security modules), VaultScan (biometric terminals), VaultGate (network appliance).

**Software** — VaultCrypt (encryption), VaultAccess (zero-trust IAM), VaultBackup (encrypted backup/DR), VaultMonitor (SIEM threat detection).

**Tagline** — *"Privacy first. Security in service."* · *"Your data. Your rules. VaultWares."*

---

## Index

| File / folder | Purpose |
| --- | --- |
| `colors_and_type.css` | Canonical CSS variables — palette, type scale, spacing, radii, shadows, motion, glass. Import this in every prototype. |
| `assets/logos/` | Wordmark variants, minimal "V" mark in gold/ink/mono, the wave logo, the bilingual SVG. |
| `assets/favicons/` | Browser favicons by color and size. |
| `preview/` | Design-system tab cards — palettes, type specimens, components, brand. |
| `ui_kits/docs-site/` | Mintlify-style docs site (the live `docs.vaultwares.com` shape) recreated as a clickable React/JSX prototype. |
| `ui_kits/brand-guide-app/` | The interactive brand-guide reference app from `vault-themes/examples/brand-guide`. |
| `SKILL.md` | Cross-compatible Claude Skill definition (brand voice + token use + asset inventory). |

---

## Content fundamentals

VaultWares copy is **calm, precise, human, principled, and competent**. Writing should feel closer to a premium notebook than a threat-intelligence dashboard.

**Voice rules**

- Second person ("you"), active voice. The product speaks plainly to the reader.
- State what is true. Do not perform urgency. A locked vault is a locked vault — not "fortress-grade protection."
- Bilingual parity (EN / Quebec FR) is required for any user-facing string. Layouts must tolerate French strings being **15–20% longer** than English.
- Tagline anchors: *"Privacy first. Security in service."* / *"La confidentialité d'abord. La sécurité au service."*
- No emoji in product UI or marketing surfaces. Icon system carries that load.

**Casing**

- Sentence case for buttons, menu items, and titles ("Continue", "Initialize device", "Vault secured").
- Title Case only for proper nouns and theme/product names ("Golden Slate", "VaultDrive Enterprise").
- Product names are one word, gold-cap V: **VaultWares**, **VaultDrive**, **VaultHSM**.

**Forbidden language**

| Avoid | Use instead |
| --- | --- |
| "just", "simply", "easy" (unless factually proven) | Describe the actual steps. |
| "military-grade encryption" | Name the algorithm. ("AES-256-XTS") or just *"Vault secured."* |
| "hacker-proof", "bulletproof" | Honest scope. ("Tamper-evident", "Verified by FIPS 140-3 Level 3") |
| "CRITICAL SECURITY WARNING" | "We noticed something. Here's what to do." |
| "Proceed" | "Continue" |
| Competitor product names | — |

**Voice examples — show, don't tell**

| Instead of… | We say… |
| --- | --- |
| "Encrypted with military-grade AES-256!" | "Vault secured." |
| "Critical security warning!" | "We noticed something. Here's what to do." |
| "Proceed to authentication." | "Continue." |
| "We collect this for your security." | "This is optional and off by default." |
| "Hacker-proof your life." | "Your data. Your device. Your rules." |

**Vibe**

Calm, deliberate, technically honest. Whitespace is generous. A VaultWares product succeeds when a user trusts it without reading the privacy policy and prefers it not because they have to, but because it is better.

---

## Visual foundations

**Color**

The palette is Solarized-inspired: deep teal `#002B36` and warm paper `#FDF6E3` as the two grounds, with gold `#CC9B21` as the brand accent (the "V" in the wordmark). Cyan `#21B8CC` is reserved for interactivity. Green `#4ECC21` is success / secured. Burgundy `#A63D40` is destructive. Gold is the deliberate counter-signal: where every other security brand uses cold blue or alarm red, gold reads as craft, value, and considered design.

Never: pure black backgrounds, neon green, gradient washes that span screens, terminal aesthetics. Dark mode is **deep teal**, not black; light mode is **warm paper**, not stark white.

**Typography**

UI: `"Segoe UI Semilight" → "Segoe UI" → "Inter" weight 300`. Monospace: `"JetBrains Mono" → "IBM Plex Mono"`. Inter is loaded from rsms.me as the cross-platform fallback (Segoe UI is Windows-only). Weight 300 reads thoughtful, not loud — this is intentional. We do not use heavy weights, condensed faces, or terminal monospace UI.

**Spacing & rhythm**

8px base scale: `4 8 12 16 24 32 40 48 64`. Generous whitespace; never crowded. Default content max-width ≈ 1100px on docs surfaces.

**Backgrounds**

Solid paper or solid base by default. Imagery is sparse, never decorative. When imagery appears it is product photography (matte hardware on neutral paper) or schematic line diagrams — **never** stock-photo people pointing at screens, **never** code-rain, **never** padlocks. Full-bleed gradients are forbidden; subtle radial fades from `paper-bright → paper` are allowed for hero panels only.

**Borders & dividers**

Hairlines at `rgba(0,43,54,0.14)` on paper, `rgba(253,246,227,0.18)` on dark. 1px is the default; 2px reserved for focused/selected states. No double-borders, no inset shadows pretending to be borders.

**Shadows**

Soft and paper-like. The system has four steps: `sm`, `md`, `lg`, `panel`. All blue-tinted (`rgba(0,43,54,…)`), never neutral grey, never black. **No neon glows.** A focus ring is a 3px cyan halo at 35% alpha — the only "glow" in the system.

**Corner radii**

Standard: `4 / 8 / 12 / 16 / 20`. Buttons and inputs use `8px`. Cards use `12–16px`. Glass panels and hero surfaces use `20px`. Pills (badges) use `999px`. Never sharp corners except in dense data tables.

**Cards**

- Light mode: `#FDFCF7` surface, 1px `rgba(0,43,54,0.14)` border, `12–16px` radius, `--vault-shadow-md`.
- Dark mode: surface offset from base (`#0E3A47`), 1px `rgba(253,246,227,0.18)` border, same shadow scale (still blue-tinted).
- No gradient cards. No left-border accent stripes. No emoji-as-icon cards.

**Buttons & states**

| State | Treatment |
| --- | --- |
| Default | Solid gold (`#CC9B21`) on ink text, or outlined cyan for secondary. |
| Hover | Background steps to `gold-muted` `#B78C1E` (light) / `gold-light` `#E5C06A` (dark). 180ms `ease-out`. |
| Press | Background holds; transform `scale(0.98)`; 120ms. |
| Focus | 3px cyan halo via `--vault-shadow-focus`, no outline jump. Always visible in both modes. |
| Disabled | Opacity `0.45`, no pointer events. Never grey out interactive color — desaturate. |

State should never depend on color alone — pair with iconography, copy, or position.

**Motion**

Subtle. **No** infinite decorative loops by default. Three durations: `120ms` for taps, `180ms` for state changes, `240ms` for entry/exit. Easing: `ease-out` for entries, `ease-in-out` for state transitions. Page transitions: opacity + 6–10px translateY, never slide-across or scale-from-nothing.

**Hover states**

- Cards: shadow steps up one level (`md → lg`), border darkens by ~4% alpha.
- Links: cyan underline thickens from 1px to 2px, no color shift.
- Icons: opacity `0.7 → 1.0`, no rotation, no bounce.

**Glass UI** (the optional accent)

Glass is a *supporting* effect, not the identity. Use it for: elevated overlays, command palettes, settings panels, focus moments. **Never** full-page blur. Three blur levels: `8 / 16 / 20px`. Light glass: `rgba(253,252,247,0.62)` with `border-light` hairline. Dark glass: `rgba(74,84,89,0.50)` with `border-dark` hairline.

**Layout rules**

- Generous side margins; never edge-to-edge text on desktop. Hero sections use `clamp(48px, 6vw, 96px)` vertical padding.
- 12-column grid for docs / app surfaces; 4-column for marketing.
- Sidebars are `260–280px`. Persistent in dark, light, or paper mode.
- Sticky elements are subtle: `surface-elevated` background (86% paper), `border-bottom: 1px solid divider`, no shadow until scrolled.

**Transparency / blur**

Reserved. Used for: glass panels, sticky headers (`backdrop-filter: blur(8px)`), modals (16px). Body content never sits on translucent backgrounds.

**Imagery vibe**

Cool and quiet. If photography is used, it leans neutral or slightly cool, with paper-toned warmth in the highlights. No saturation pushes. No grain. Hardware shots: white seamless or paper background, soft top light, hero specular on the gold V. Schematics: 1.5px `vault-ink` lines on `vault-paper`, no fills, callouts in `vault-cyan`.

---

## Iconography

**Lucide is the default icon system.** The brand-guide example app at `vault-themes/examples/brand-guide` imports from `lucide-react` (`Check`, `Copy`, `Eye`, `Languages`, `ShieldCheck`, `Sparkles`, `Lock`, etc.). Lucide's stroke style — 1.5–2px, rounded joins, square caps — matches our line weight.

The Mintlify docs site (`docs.json`) uses **FontAwesome** icon names (`shield-halved`, `microchip`, `usb-drive`, `book-open`, `wand-magic-sparkles`). When recreating the docs surface we substitute the closest Lucide equivalent for visual consistency.

**Rules**

- 1.5–2px stroke, never filled (except the minimal-V mark logo). Match the stroke weight of nearby type.
- Icon size pairs with type: `16px` next to body, `20px` next to headings, `24px` for primary navigation.
- Icon color follows text color, *not* the brand accent — except in two cases: (1) a primary action button's icon takes the button's text color; (2) a status pill's icon takes the semantic color (`success` green, `danger` burgundy).
- **No emoji** in product UI, marketing, or docs. Icon assets carry that load.
- **No unicode glyphs as icons** (no `→` arrows, no `✓` check marks). Use Lucide.
- **Do not draw replacement SVGs.** If the design needs an icon Lucide doesn't have, ask before substituting.

**Logo as icon**

The minimal V mark at `assets/logos/vaultwares-minimal-{gold,ink,mono}-filled.png` is used at favicon scale (16–32px). It is **not** a UI icon — it represents the brand only.

| Variant | Use |
| --- | --- |
| `…-gold-filled.png` | Default on dark backgrounds, app titlebars, dock icons. |
| `…-ink-filled.png` | Light backgrounds, document headers. |
| `…-mono-filled.png` / `-mono-v2.png` | Single-color contexts, embossing, watermarks. |

Never scale the minimal mark below 16×16px — switch to the full SVG wordmark instead. Never recolor with CSS filters; choose the right variant.

**Wordmark**

Live SVGs at `assets/logos/vaultwares-wordmark-{light,dark}.svg` (from the docs repo) and `assets/logos/vaultwares-logo-{dark,mono}.svg` (from the brand repo). Minimum height: **32px** digital, **10mm** print. Clear space: ½ logo height. Never stretch, recolor, rotate, or filter.

---

## Caveats

- **Font substitution flagged.** Segoe UI Semilight is Windows-only and not redistributable. We load **Inter weight 300** from rsms.me as the cross-platform stand-in. The brand-guide example app does the same. If you have licensed Segoe UI files, drop them in `fonts/` and update `--vault-font-sans`.
- **Icon system substitution flagged.** The Mintlify docs site references FontAwesome by name in `docs.json`. The recreated docs UI kit uses **Lucide** instead (CDN), to match the React brand-guide app. Confirm if you want a FontAwesome variant.
- **Theme color conflict.** `docs.json` declares `primary: #1E40AF`. The brand source of truth uses gold `#CC9B21`. We followed the brand repo. Update one or the other when you decide.
