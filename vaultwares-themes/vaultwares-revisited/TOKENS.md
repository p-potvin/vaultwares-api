# VaultWares Revisited: Tokens & Palettes

All colors, fonts, and spacing constraints are defined by these core tokens. Never use raw hex values in the project.

## 1. Color Palettes

### Warm Mode

| Token | Hex | Usage |
|---|---|---|
| `--vault-warm-bg` | `#F5F1E8` | Deepest background for warm mode (the "desk") |
| `--vault-warm-raised` | `#FCFAF5` | Elevated surfaces, cards, input fields ("paper") |
| `--vault-warm-muted` | `#ECE5D8` | Disabled states, subtle backgrounds, tertiary surfaces |
| `--vault-warm-border-subtle` | `rgba(22, 19, 32, 0.08)` | Dividers, borders in warm mode |

### Console Mode

| Token | Hex | Usage |
|---|---|---|
| `--vault-console-bg` | `#161320` | Base canvas, app root background |
| `--vault-console-surface`| `#1F1A2B` | Default container background |
| `--vault-console-raised` | `#2A2340` | Highly elevated layer, popovers, active cards |
| `--vault-console-elevated`| `#31274A` | Modals, tooltips, drag states |
| `--vault-console-border-subtle`| `rgba(255, 255, 255, 0.06)` | Lines separating console panels |
| `--vault-console-text-secondary`| `rgba(237, 230, 255, 0.72)` | Muted text in console mode |

### Brand Accents

| Token | Hex | Usage |
|---|---|---|
| `--vault-console-gold` | `#D6A441` | Primary brand accent for the terminal. Links, highlights, primary buttons. |
| `--vault-console-violet` | `#B07CFF` | Secondary accent. Focus rings, secondary highlights, sync indicators. |

### Signal Colors (Status)

The "Signal" palette replaces standard red/green/yellow with a neon, LED-like palette.

| Token | Hex | Meaning |
|---|---|---|
| `--vault-signal-online` | `#6BE675` | Success, operational, secured, healthy |
| `--vault-signal-relay` | `#55D6FF` | Info, processing, neutral operations |
| `--vault-signal-sync` | `#B07CFF` | Syncing, connecting, secondary states |
| `--vault-signal-warning` | `#F0B94B` | Warnings, intermediate failures |
| `--vault-signal-alert` | `#FF6B7A` | Critical failures, destructive actions |

## 2. Typography Tokens

- `--font-sans`: `"Segoe UI", "Inter", "ui-sans-serif", "system-ui", sans-serif`
- `--font-mono`: `"JetBrains Mono", "Lucide Console", "ui-monospace", "SFMono-Regular", monospace`
