---
name: VaultWares
description: Use whenever you design for VaultWares — the privacy-first cybersecurity company shipping hardware (VaultDrive, VaultHSM, VaultScan, VaultGate) and software (VaultCrypt, VaultAccess, VaultBackup, VaultMonitor). Calm, considered, bilingual EN/Quebec-FR. Solarized-inspired teal + paper grounds with gold (#CC9B21) accent and cyan (#21B8CC) interaction. Light Inter (or Segoe UI Semilight) typography, 8px spacing, hairline borders, soft blue-tinted shadows. The opposite of dark-terminal "hacker" security branding.
---

# VaultWares Design System — Skill Brief

## When to use this skill

Apply for any VaultWares-branded surface: docs site, customer portal, marketing pages, slide decks, product UI, hardware mockups, support emails, error states, FR translations.

## Tagline & promise

- **Tagline.** *"Privacy first. Security in service."*
- **FR.** *"La confidentialité d'abord. La sécurité au service."*
- **Promise.** Your data. Your device. Your rules.

## Voice — calm · precise · human · principled · competent

Speak the way a thoughtful security engineer would: plainly, second person, active voice. State what is true. Do not perform urgency. A locked vault is a locked vault.

**Always**

- Sentence case for buttons, titles, menu items.
- Bilingual EN ↔ Quebec FR parity. FR strings run **15–20% longer** — every layout must tolerate it.
- Name the actual algorithm or certification when relevant ("AES-256-XTS", "FIPS 140-3 Level 3").
- Honest scope: "tamper-evident", not "tamper-proof".

**Never**

- Filler words: "just", "simply", "easy" (unless factually proven).
- Marketing absolutes: "military-grade", "hacker-proof", "bulletproof", "fortress-grade".
- Caps-lock alarms: "CRITICAL SECURITY WARNING" → use *"We noticed something. Here's what to do."*
- "Proceed" → *"Continue."*
- Emoji anywhere in product, docs, or marketing.
- Unicode glyphs as icons (`→`, `✓`). Use Lucide.

**Replacements**

| Avoid | Use |
| --- | --- |
| Encrypted with military-grade AES-256! | Vault secured. |
| Critical security warning! | We noticed something. Here's what to do. |
| Proceed to authentication. | Continue. |
| We collect this for your security. | This is optional and off by default. |
| Hacker-proof your life. | Your data. Your device. Your rules. |

## Design tokens — `colors_and_type.css`

Always import `colors_and_type.css` at the top of every prototype. It exposes:

```css
--vault-base: #002B36;     /* deep teal — dark surface */
--vault-paper: #FDF6E3;    /* warm paper — light surface */
--vault-paper-bright: #FDFCF7;
--vault-deep-sea: #0A2540;

--vault-gold: #CC9B21;     /* primary accent — V mark */
--vault-gold-muted: #B78C1E;
--vault-gold-light: #E5C06A;

--vault-cyan: #21B8CC;     /* interaction, focus, links */
--vault-green: #4ECC21;    /* success / vault secured */
--vault-burgundy: #A63D40; /* destructive / error */

--vault-slate: #4A5459;    /* secondary text/surface */
--vault-muted: #586E75;    /* captions, metadata */

--vault-font-sans: "Segoe UI Semilight", "Segoe UI", "Inter", system-ui, sans-serif;
--vault-font-mono: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace;
```

Spacing 8px scale: `4 8 12 16 24 32 40 48 64`. Radii: `4 / 8 / 12 / 16 / 20` and pill `999`. Motion: `120 / 180 / 240 ms`. Glass blur: `8 / 16 / 20`. Borders: 1px hairlines (`rgba(0,43,54,0.14)` on paper, `rgba(253,246,227,0.18)` on dark).

Use Inter weight 300 (load from rsms.me) as the cross-platform fallback for Segoe UI Semilight. The light weight is intentional — VaultWares does not shout.

## Visual rules of thumb

- Two grounds: deep teal `#002B36` (dark) or warm paper `#FDF6E3` (light). Not pure black, not stark white.
- Gold is the brand signal. Cyan is the interaction signal. Never swap their roles.
- Hairline borders, not heavy ones. Blue-tinted shadows, not grey or black.
- Cards: `12–16px` radius. Buttons/inputs: `8px`. Glass / hero: `20px`. Pills: `999px`.
- One focus ring: 3px cyan halo at 35% alpha (`--vault-shadow-focus`).
- No infinite decorative motion. State changes settle in 180ms.
- Generous whitespace. Default content max-width ≈ 1100px on docs.

**Forbidden**

- Pure black or stark white surfaces · neon green · rainbow gradients · padlock-with-lightning illustrations · code-rain · binary streams · stock photo of person pointing at a screen · drop shadow with `#000` · left-border accent stripes on cards · rounded-pill-with-tiny-icon "AI" badges · emoji icons · terminal aesthetic chrome.

## Iconography

- **Lucide** is the default icon set. 1.5–2px stroke, rounded joins. Match nearby type weight.
- 16px next to body · 20px next to headings · 24px in primary nav.
- Icon color follows text color, not the brand accent — except in primary buttons (icon = button text color) and status pills (icon = semantic color).
- The minimal V mark is **brand only**, never UI. Use gold-filled on dark, ink-filled on light, mono in single-color contexts.
- Mintlify FontAwesome names (`shield-halved`, `microchip`, `usb-drive`) get substituted with their Lucide equivalents (`shield`, `cpu`, `hard-drive`).

## Components

| Component | Treatment |
| --- | --- |
| **Primary button** | Solid `gold` on `ink` text. Hover → `gold-muted`. Press → `scale(0.98)`. Focus → cyan halo. |
| **Secondary button** | Transparent, `ink` text, hairline border. Hover border → cyan, text → deep cyan. |
| **Ghost button** | Transparent, `ink` text. Hover background `rgba(0,43,54,0.05)`. |
| **Destructive button** | Transparent, `burgundy` text, burgundy hairline. Hover background → `danger-bg`. |
| **Input** | `paper-bright` surface, hairline border, 8px radius. Focus → cyan border + halo. Error → burgundy border + faint burgundy halo. |
| **Card (light)** | `#FDFCF7` surface, hairline border, 12–16px radius, `shadow-md`. |
| **Card (dark)** | `#0E3A47` surface, light hairline border, same shadow scale. |
| **Status pill** | `999px` radius, semantic background tint at ~13% alpha + matching dot + dark semantic text. |
| **Compliance badge** | Mono font, `4px` radius, dark background with gold text *or* paper with hairline border. |
| **Glass panel** | `rgba(253,252,247,0.62)` light · `rgba(74,84,89,0.50)` dark · `backdrop-filter: blur(16px)` · 20px radius. |
| **Banner / callout** | 12px radius, hairline border in semantic color, faint semantic background tint, semantic icon at 18px. |

## Asset inventory

- `assets/logos/vaultwares-wordmark-{light,dark}.svg` — primary wordmark, gold V with cyan inset.
- `assets/logos/vaultwares-logo-{dark,mono}.svg` — alternate wordmarks.
- `assets/logos/vaultwares-minimal-{gold,ink,mono,mono-v2}-filled.png` — favicon-scale V mark.
- `assets/logos/branding-fr-en.svg` — bilingual lockup.
- `assets/logos/vaultwares-wave-logo.png` — wave variant for marketing only.
- `assets/logos/favicon.svg` + `assets/favicons/*.png` — browser/OS favicons.
- `assets/icons/*` — small inventory of Lucide-equivalent product icons.

## Bilingual rules

- Every user-facing string ships with EN + FR. Use the EN/FR toggle pattern shown in `ui_kits/docs-site/index.html`.
- French is Quebec French — *courriel*, not *email*; *fichier*, not *file*. Avoid Anglicisms.
- Layouts use `min-content` columns or `flex-wrap`, not fixed widths, so 20% longer FR strings reflow cleanly.
- Date format: `April 24, 2026` (EN) · `24 avril 2026` (FR).

## Caveats / known substitutions

1. **Segoe UI Semilight** is Windows-only and not redistributable. Inter weight 300 from rsms.me is the cross-platform stand-in. Drop licensed Segoe UI files into `fonts/` to swap.
2. **FontAwesome → Lucide.** The Mintlify `docs.json` references FontAwesome by name; we render with Lucide for visual consistency with the brand-guide React app. Confirm if a FontAwesome variant is needed.
3. **Theme color conflict.** `docs.json` says `primary: #1E40AF`; brand source of truth says gold `#CC9B21`. We followed the brand repo. Reconcile when the time comes.
