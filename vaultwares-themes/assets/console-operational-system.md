# VaultWares Console Operational System

> Added from `C:\Users\Administrator\Desktop\VaultWares Console` on May 22, 2026.

This layer extends the existing VaultWares brand without replacing it. Use it for
web dashboards, operational landing pages, app shells, relay telemetry, and
surfaces where the user should feel they are entering a working VaultWares
control environment.

## Philosophy

The console system combines warm physical trust with a focused operational dark
surface:

- Warm shell surfaces use paper and raised-paper tones for navigation, identity,
  and low-pressure context.
- Console surfaces use deep aubergine instead of pure black, with violet and cyan
  signals for live infrastructure.
- Gold remains the brand value signal and should appear on marks, primary
  assertions, selected states, and high-value controls.
- Colored LEDs are operational states, not decoration. Use them beside status
  labels and telemetry only.
- The system should feel calm, precise, and actively running; avoid hacker
  theater, code rain, alarm copy, and oversized threat imagery.

## Tokens

| Token | Hex | Role |
| --- | --- | --- |
| `vault.warmBg` | `#F5F1E8` | Warm page or shell background |
| `vault.warmRaised` | `#FCFAF5` | Raised warm panels and nav rails |
| `vault.warmMuted` | `#ECE5D8` | Muted warm controls and selected nav |
| `vault.consoleBg` | `#161320` | Primary operational surface |
| `vault.consoleSurface` | `#1F1A2B` | Header and low elevation console panels |
| `vault.consoleRaised` | `#2A2340` | Cards, chips, and table headers |
| `vault.consoleElevated` | `#31274A` | Icon wells and selected raised controls |
| `vault.consoleGold` | `#D6A441` | Brand mark, primary action, assertions |
| `vault.consoleViolet` | `#B07CFF` | Secondary accent and sync telemetry |
| `vault.signalOnline` | `#6BE675` | Healthy / online |
| `vault.signalRelay` | `#55D6FF` | Relay / transport |
| `vault.signalSync` | `#B07CFF` | Sync / distributed state |
| `vault.signalWarning` | `#F0B94B` | Delayed / attention |
| `vault.signalAlert` | `#FF6B7A` | Error / alert |

## UI Guidelines

- Use a warm side rail or warm hero frame when the surface needs brand grounding.
- Use console dark for working regions, product grids, telemetry panels, and
  account or checkout flows.
- Use 28-32 px radii for large console cards, 16-20 px radii for controls, and
  1 px low-alpha borders.
- Pair every live color with a text label. Color alone is not enough.
- Keep motion subtle. The only repeating motion in this layer is a slow LED pulse
  for live status indicators.
- Prefer inline SVG icons from `components/react/vaultwares-icons.tsx` for
  operational concepts that Lucide does not cover.

## Icon Set

The console icon set adds operational glyphs:

- `RelayCoreIcon`
- `RelayDistributedIcon`
- `UtilityBlockIcon`
- `UtilityChannelIcon`
- `VWAngularIcon`
- `VWCoreIcon`

Use these as inline SVG React components or as symbols from
`assets/icons/vaultwares-console-icons.svg`.
