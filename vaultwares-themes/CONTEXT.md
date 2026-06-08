# VaultWares Agent Context Brief

Use this when an agent, IDE assistant, or human needs the VaultWares brand and
style rules without reading the whole repository.

## Source Of Truth

| Need | Read |
| --- | --- |
| Full agent and style rules | `AGENTS.md` |
| Brand guide | `brand/brand-guide.md` |
| Philosophy and voice | `brand/philosophy.md` |
| Tokens | `brand/tokens/tokens.ts` |
| Tailwind mapping | `brand/tokens/tailwind.config.ts` |
| Bilingual strings | `brand/i18n/brand.i18n.ts` |
| Logos and icons | `assets/README.md` |
| Consumer repo propagation | `theme-manager/tools/sync_submodule_rules.py` |

## Who VaultWares Is

VaultWares builds privacy-first productivity and security tools. The priority
order is:

1. Privacy for individuals
2. Security in service of privacy
3. Functionality that stays understandable
4. Performance
5. Scalability
6. Developer experience

Tagline:

- EN: Privacy first. Security in service.
- QC/FR: La confidentialite d'abord. La securite au service.

## Voice

VaultWares is calm, precise, human, and technically rigorous. It is not alarming,
corporate, hacker-coded, or jargon-heavy.

Use:

- "We do not track you. Here is what we store, and why."
- "Turn this on if you want analytics. It is off by default."
- "Vault secured."

Avoid:

- "Military-grade encryption"
- "Hacker-proof"
- "Critical security warning"
- Fear-based or surveillance-justifying copy

## Visual System

Core tokens:

| Token | Value | Use |
| --- | --- | --- |
| `vault.base` | `#002B36` | Deep dark background |
| `vault.paper` | `#FDF6E3` | Warm light background |
| `vault.gold` | `#CC9B21` | Primary accent and logo mark |
| `vault.cyan` | `#21B8CC` | Links, focus, interactive affordance |
| `vault.green` | `#4ECC21` | Success / secured state |
| `vault.burgundy` | `#A63D40` | Error / destructive |
| `vault.slate` | `#4A5459` | Secondary surfaces and text |
| `vault.muted` | `#586E75` | Captions and tertiary text |

Rules:

- No pure black + neon green.
- No terminal or Matrix aesthetic for product UI.
- Use both light and dark modes.
- Body contrast target is WCAG AA, 4.5:1 or better.
- Use 8px spacing rhythm.
- Use Segoe UI Semilight / Segoe UI / Inter / system-ui.
- Use glass sparingly: overlays, elevated cards, command surfaces.

## Agent Completion Checklist

- Read `AGENTS.md` before editing this repo.
- Check token paths before changing imports.
- Keep docs and demo paths in sync.
- Keep consumer guidance pointing to this repo, not copied duplicates.
- Run Python and demo checks when touching tooling or the brand guide.
