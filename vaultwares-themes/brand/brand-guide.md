# VaultWares Brand Guide

This is the maintainable source for agents and humans. The old exported HTML
bundle was useful as a visual draft, but this file is now the source of truth.

## Foundation

VaultWares builds privacy-first tools that are secure by default and practical
for real people. The brand is not fear-driven security theatre. It is calm,
clear, bilingual, and technically honest.

Priority order:

1. Privacy for individuals
2. Security in service of privacy
3. Functionality
4. Performance
5. Scalability
6. Developer experience

Tagline:

- EN: Privacy first. Security in service.
- QC/FR: La confidentialite d'abord. La securite au service.

## Voice And Tone

VaultWares is calm, precise, human, principled, and competent.

Use:

- "We do not track you. Here is what we store, and why."
- "Turn this on if you want analytics. It is off by default."
- "Vault secured."
- "Continue."

Avoid:

- "Military-grade encryption"
- "Hacker-proof"
- "Critical security warning"
- "Proceed"
- Any copy that uses security language to justify unnecessary collection

French and Quebec French should be first-class, not an afterthought. Layouts
must allow 15-20% more room for French text.

## Color System

Use named tokens from `brand/tokens/tokens.ts`. Do not hardcode ad hoc hex
values in reusable app code.

| Role | Token | Value | Use |
| --- | --- | --- | --- |
| Dark background | `vault.color.base` | `#002B36` | Deep teal foundation |
| Light background | `vault.color.paper` | `#FDF6E3` | Warm paper surface |
| Bright surface | `vault.color.paperBright` | `#FDFCF7` | Elevated light panels |
| Primary accent | `vault.color.gold` | `#CC9B21` | Brand mark, key actions |
| Interactive | `vault.color.cyan` | `#21B8CC` | Links, focus, controls |
| Success | `vault.color.green` | `#4ECC21` | Secured/success states |
| Error | `vault.color.burgundy` | `#A63D40` | Destructive/error states |
| Secondary | `vault.color.slate` | `#4A5459` | Dark surfaces, secondary text |
| Muted | `vault.color.muted` | `#586E75` | Captions, metadata |

Never use pure black + neon green or terminal-style product UI.

## Typography

Primary UI stack:

```text
Segoe UI Semilight, Segoe UI, Inter, system-ui, sans-serif
```

Use lighter weights for calm, professional surfaces. Use monospaced fonts only
for developer-facing code blocks, logs, or diagnostics.

## Logo Use

Preferred logo assets live under `assets/logos/`.

- Use the full VaultWares wordmark when space allows.
- Use minimal/favicons only for small surfaces.
- Do not use floating generic lock icons.
- Keep clear space around the logo.
- Do not recolor the standard gold/cyan mark casually.

## Glass UI

Glass is a supporting effect, not the whole identity.

Use glass for:

- Elevated cards over meaningful backgrounds
- Command palettes
- Settings panels
- Preview overlays
- Small interactive hero moments

Avoid:

- Full-page blur
- Low-contrast text over glass
- Heavy decorative animation loops
- Glass effects that obscure the task

The examples in `components/glass/` and `examples/brand-guide/` are adapted from
the local `glass-ui` repo and converted to VaultWares tokens where practical.

## Accessibility

- Body contrast target: WCAG AA, 4.5:1 or better.
- Large text and UI contrast target: 3.0:1 or better.
- Focus states must be visible in both light and dark modes.
- Do not rely on color alone for state.

## Updating This Guide

1. Update `brand/brand-guide.md`.
2. Update `brand/tokens/` if the change affects reusable visual values.
3. Update `brand/i18n/brand.i18n.ts` if visible copy changes.
4. Update `examples/brand-guide/` if the visual demo should show the change.
5. Run the checks in `README.md`.
