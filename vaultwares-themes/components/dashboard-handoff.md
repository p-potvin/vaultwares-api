# Dashboard Design Handoff

Normative spec for the VaultCentral dashboard — and any VaultWares product
surface that wants to inherit the same visual + motion language. Source files:

- `vault-central/src/styles/globals.css` — token definitions and primitive
  classes (`.vault-card`, `.vault-btn`)
- `vault-central/src/components/VaultDashboard.tsx` — reference implementation

The goal is calm, sleek, and honest. Motion is restrained, animations never
shift layout during normal flow, surfaces are quiet by default and rise only
on direct interaction. We do not copy any specific OS aesthetic; we share the
underlying principles that make those aesthetics feel cohesive.

## Overview

VaultCentral is a privacy-first media vault. The dashboard is the user's
primary surface — a list-and-grid layout for saved videos and links, with a
sidebar of view controls and a settings modal. Themes (10 of them) swap
foundational colors but the behavior, motion, and structural tokens here are
theme-independent.

## Layout

The dashboard is a fixed-height single-page app: header (64px) → split
viewport (sidebar + main scroll area) → optional modal layer above. No
horizontal scrolling at any breakpoint.

| Breakpoint | Behavior |
|------------|----------|
| ≥1280px (xl) | Sidebar 256px expanded, 16px-wide collapse rail. Cards in 2–5 columns depending on viewSize. |
| 1024–1279px (lg) | Same as xl with one fewer column at viewSize 3 (4 cols → 3 cols at viewSize 3 etc.). |
| 768–1023px (md) | Same general layout, two-column grids dominate. |
| <768px | Single-column grids; sidebar still toggleable but covers less of the viewport. |

The main scroll area uses infinite scroll: `sectionLimit` increments by 20
when the user reaches 1.5× viewport height from bottom, throttled to 300ms.

## Design tokens

### Motion

Defined as CSS custom properties at `:root` in `globals.css`. Use these via
`var(--name)` rather than re-deriving curves or durations elsewhere.

| Token | Value | Use |
|-------|-------|-----|
| `--vault-ease-soft` | `cubic-bezier(0.16, 1, 0.3, 1)` | Default for all entrance, hover, and state transitions. Decelerates through ~80% of travel and lands quietly. |
| `--vault-ease-standard` | `cubic-bezier(0.4, 0, 0.2, 1)` | Reserved for layout-affecting transitions (sidebar collapse, modal scale). Symmetric in/out. |
| `--vault-dur-fast` | `110ms` | Hover/focus/active state changes on small elements (buttons, chips). |
| `--vault-dur-base` | `180ms` | Default for everything else (cards, modals, toasts). |
| `--vault-dur-slow` | `280ms` | Theme cross-fade and full-surface re-color only. Avoid for normal interactions. |

**Rule**: animations target `opacity` and small `transform` (≤2px translate,
no scale unless modal entrance). No `width`/`height`/`margin` transitions in
normal flow — they cause reflow and feel heavy. The only exception is the
sidebar collapse animation, which is intentional and infrequent.

### Surfaces

| Token | Value | Use |
|-------|-------|-----|
| `--vault-radius-sm` | `6px` | Buttons, input fields, small chips. |
| `--vault-radius-md` | `10px` | Cards, modal corners, thumbnail containers. |
| `--vault-radius-lg` | `14px` | Locked banner, large overlays. |
| `--vault-shadow-resting` | three-layer (1px ring + 2px tight + 12px diffuse) | All surfaces at rest. |
| `--vault-shadow-hover` | three-layer (1px ring + 4px tight + 28px diffuse) | Cards on hover. The diffuse layer doubles in spread; the tight layer is the perceptual cue. |

The shadow stack is designed for both light and dark themes. Each layer uses
`rgb(0 0 0 / X)` so it composes correctly over any token background. Don't
substitute single-shadow `box-shadow: 0 4px 6px rgba(0,0,0,.1)` — it reads
flat against dark surfaces.

### Color

Color tokens live in `vault-themes.css` (auto-generated from the theme
manager) and are referenced via existing CSS variables: `--vault-bg`,
`--vault-text`, `--vault-border`, `--vault-card-bg`, `--vault-muted`,
`--vault-accent`, `--vault-accent-hover`. The dashboard never hardcodes hex
values; it composes via `color-mix()` against tokens for hover tints:

```css
background-color: color-mix(in srgb, var(--vault-accent) 12%, transparent);
border-color: color-mix(in srgb, var(--vault-accent) 60%, var(--vault-border));
```

This keeps hover/focus tints aligned with the active theme regardless of which
of the 10 themes the user is on.

### Typography

Single primary stack defined as `--vault-font` in `globals.css`:

```
Segoe UI Semilight, Segoe UI, Inter, system-ui, sans-serif
```

Letter-spacing default is `-0.005em` on the body element — barely perceptible
tighten that aligns with modern UI. Monospace is used only for technical
values (URLs, timestamps in metadata badges).

| Role | Class | Weight | Size | Tracking |
|------|-------|--------|------|----------|
| Page title (header H1) | `text-xl font-bold tracking-tight` | 700 | 20px | `-0.025em` |
| Section heading (group name) | `text-base font-semibold tracking-tight` | 600 | 16px | `-0.015em` |
| Card title | `text-[15px] font-bold leading-snug` | 700 | 15px | default |
| Sidebar label | `text-[11px] font-semibold tracking-tight` at 85% muted | 600 | 11px | `-0.015em` |
| Chip / type tag | `text-[10px] font-medium tracking-tight` | 500 | 10px | `-0.015em` |
| Body / metadata | `text-[11px] text-vault-muted` | 400 | 11px | default |
| Toast message | `text-[13px] font-medium tracking-tight` | 500 | 13px | `-0.015em` |

**Forbidden**: `uppercase`, `tracking-widest`, `font-black`. The pre-refresh
dashboard used these heavily and the result felt like a terminal. Reserve
`uppercase` for technical badges where casing carries semantic meaning
(rare).

## Components

### `.vault-card`

Card surface for the entry tiles in the main grid.

| Aspect | Default | Hover | Active | Notes |
|--------|---------|-------|--------|-------|
| Border | `1px solid var(--vault-border)` | `1px solid color-mix(35% accent, border)` | — | Border color shifts toward accent without becoming dominant. |
| Background | `var(--vault-card-bg)` | unchanged | — | Hover does not change the fill — only border + shadow rise. |
| Shadow | `--vault-shadow-resting` | `--vault-shadow-hover` | — | Diffuse layer roughly doubles, giving the lift cue. |
| Radius | `--vault-radius-md` | unchanged | — | |
| Transform | none | none | none | **Do not** translate the card on hover. Earlier versions used `translateY(-2px)` and made the entire grid jitter as the cursor moved. |
| Transition | — | 180ms `--vault-ease-soft` on `box-shadow, border-color, background-color` | — | |

### `.vault-btn`

The shared button primitive. Default is "ghost" (transparent background,
quiet border). Apply variant classes inline for emphasis (e.g. `bg-vault-accent text-vault-bg`).

| Aspect | Default | Hover | Active | Disabled |
|--------|---------|-------|--------|----------|
| Padding | `6px 14px` | — | — | — |
| Font | `12px / 500 / -0.015em` | — | — | — |
| Border | `1px solid var(--vault-border)` | `color-mix(60% accent, border)` | — | unchanged, opacity 45% |
| Background | transparent | `color-mix(12% accent, transparent)` | `color-mix(18% accent, transparent)` | — |
| Color | `var(--vault-text)` | `var(--vault-text)` | — | — |
| Transform | none | none | `translateY(0.5px)` | — |
| Cursor | pointer | — | — | not-allowed |
| Transition | — | 110ms `--vault-ease-soft` on bg, border, color, transform | — | — |

The press state nudges 0.5px down — barely visible but felt. The hover state
deliberately does **not** invert background-and-text; full inversion is loud
and hard to undo when the cursor moves away.

### Locked banner

Surface that appears at the top of the dashboard when the auto-lock fires.

| Aspect | Spec |
|--------|------|
| Position | fixed, top: 16px, horizontally centered, max-width 512px |
| Container | `bg-vault-cardBg` + `border` + `--vault-radius-lg` + `backdrop-blur-md` + large soft shadow |
| Padding | 20px |
| Layout | flex row, gap 16px, icon shrink-0 → text + inline PIN inputs |
| Animation in | `animate-in slide-in-from-top-4 fade-in duration-300` (ease-soft) |
| PIN inputs | 7×9 individual digit boxes, 6px radius, focus border accent, error border 60% red |
| Auto-focus | First input after 120ms (lets the slide complete first) |

When wrong PIN is entered, the icon and copy go red, all inputs clear, focus
returns to first. Submit happens automatically once all digits are entered;
no submit button is needed.

### Toast

Transient feedback after vault operations (export success, sync failed, etc).

| Aspect | Spec |
|--------|------|
| Position | fixed, bottom: 24px, right: 24px |
| Shape | rounded-full pill |
| Padding | `10px 16px` |
| Font | `13px / 500 / -0.015em` |
| Surface | `bg-{color}-500/15` + `border-{color}-500/25` + `backdrop-blur-md` |
| Color (success) | emerald-300 text |
| Color (error) | red-300 text |
| Animation in | `slide-in-from-bottom-2 fade-in duration-200` |
| Auto-dismiss | 3000ms (NOTIFICATION_CONFIG.DURATION) |

### Thumbnail (within `.vault-card`)

Holds preview video, image, or a placeholder.

- Inset stroke: `ring-1 ring-inset ring-white/5 rounded-[inherit]` — replaces
  the previous four-corner accents. One element, no animation, signals "interactive
  surface" without competing for attention.
- Hover overlay: a single 11px-radius circular play affordance, `bg-white/90`,
  fades in (opacity 0 → 1, 200ms). **No scale animation.**
- Background dim: `bg-black/0 → bg-black/15` on hover, 200ms.
- Type chip: bottom-left, 10px medium weight, sentence case ("Video" / "Link"),
  rounded-full, fades in with the overlay.

The thumbnail interior used to have four corner-accent SVGs that animated
their size on hover. Those are removed.

## States and interactions — grammar

A consistent "state grammar" across the dashboard:

| Element type | Default | Hover | Focus | Active | Disabled |
|--------------|---------|-------|-------|--------|----------|
| Button | quiet border, transparent bg | accent tint (12%) on bg + border | 4px accent ring outside element | `translateY(0.5px)` + accent tint (18%) | opacity 45%, cursor not-allowed |
| Card | resting shadow, subtle border | hover shadow + border tint (35% accent) | not focusable directly | n/a | n/a |
| Input | quiet border | unchanged | accent border + faint accent ring | n/a | opacity 50% |
| Link (anchor) | accent color, no underline | underline appears + accent-hover color | outline ring | n/a | n/a |

`:focus-visible` is mandatory — the global rule attaches a 2-layer accent
ring (4px total) to anything keyboard-focused. Never strip it.

## Animations / motion catalogue

| Element | Trigger | Animation | Duration | Easing |
|---------|---------|-----------|----------|--------|
| `.vault-card` | hover | shadow rise + border tint | 180ms | `--vault-ease-soft` |
| `.vault-btn` | hover | bg + border tint | 110ms | `--vault-ease-soft` |
| `.vault-btn` | press | 0.5px translate down | 110ms | `--vault-ease-soft` |
| Modal (settings, edit, video player) | open | scale 95→100 + fade in | 200ms | `--vault-ease-standard` |
| Toast | append | slide up 8px + fade in | 200ms | `--vault-ease-soft` |
| Toast | dismiss | slide down 8px + fade out | 500ms | `--vault-ease-soft` |
| LockedBanner | mount | slide down 16px + fade in | 300ms | `--vault-ease-soft` |
| Sidebar | toggle | width animates 0 ↔ 256px | 300ms | `--vault-ease-standard` |
| Theme change | user picks new theme | body bg + text color cross-fade | 280ms | `--vault-ease-soft` |
| Thumbnail play affordance | parent hover | opacity 0 → 1 | 200ms | default |
| Thumbnail dim overlay | parent hover | bg 0 → 15% | 200ms | default |

Notably absent: bounce/spring curves, scale-pulse loops, infinite animations
on idle elements, layout-affecting hover transitions (translate-Y on cards,
width changes on buttons). These are deliberate omissions.

## Accessibility

- All interactive elements receive `:focus-visible` rings via the global rule;
  do not override per-element.
- Color contrast: text on backgrounds meets WCAG AA (≥4.5:1) in every theme
  configuration. The auto-generated `vault-themes.css` is responsible for
  delivering compliant pairs; if you add a new theme, run a contrast check
  against `vault-text` over `vault-bg` AND `vault-text` over `vault-card-bg`.
- The locked banner has `role="alert" aria-live="polite"`; the toast has
  `role="status" aria-live="polite"` so screen readers announce them once
  without preempting in-progress speech.
- Keyboard: tab order follows DOM (header → sidebar → main → modal when
  open). Modals trap focus while open via the Esc key handler; backdrop
  click also closes them.
- The hidden test bridge (`?__vaultTest=1`) is inert in production — no a11y
  impact.

## Edge cases

| Case | Treatment |
|------|-----------|
| Empty vault | Centered illustration + muted copy ("No encrypted items found / Try scanning a new target domain or clearing your filters"). 192px tall, dashed border, low-opacity icon. |
| Long titles | `line-clamp-2` on card titles (15px, 2 lines max). Truncate-with-ellipsis on URL line below (max-width 250px). |
| Long author / actor lists | `line-clamp-1`, comma-separated. Tags overflow shows `+N` chip when more than 3. |
| Vault locked while dashboard open | LockedBanner appears, preview reads return null. The grid still renders metadata; only thumbnail blobs disappear. |
| French (15-20% longer strings) | Buttons and labels avoid fixed widths; sidebar `w-64` is the cap. Pages must tolerate 20% longer copy without wrapping in undesirable places. |
| Slow connection / FFmpeg WASM warming | PreviewThumb shows a spinner + "Processing..." badge; retries are exponentially backed off (2, 5, 15, 30s). |
| Backup very large | Backup runs in background; user gets toast on completion. Progress UI deliberately omitted — the operation is fast enough on local data and the toast is simpler. |

## Implementation pointers (vault-central reference)

- Tokens: [`src/styles/globals.css`](../../vault-central/src/styles/globals.css)
- Buttons: `.vault-btn` class. Apply variant utilities inline (e.g. `bg-vault-accent text-vault-bg` for primary).
- Cards: `.vault-card` class.
- Modals (settings, edit, video player): wrap in `fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm`, inner panel uses `animate-in zoom-in-95 duration-200`.
- Toast: see `setToastMessage` state in [VaultDashboard.tsx](../../vault-central/src/components/VaultDashboard.tsx) — auto-dismisses after 3s.
- Locked banner: `LockedBanner` component in the same file; takes `visible / pinLength / onUnlocked` props.

## Porting to other VaultWares projects

This handoff documents the dashboard surface specifically, but the token
system (motion, surfaces, typography, state grammar) is the intended
company-wide default. To reuse:

1. Copy the `:root` token block + `body` rules + `:focus-visible` rule from
   `vault-central/src/styles/globals.css` into your project.
2. Lift `.vault-card` and `.vault-btn` (or rename to your project's prefix).
3. Pull color tokens from `vault-themes.css` via the existing theme manager
   so themes stay synchronized.
4. Don't substitute different ease curves or durations. Consistency across
   products is more valuable than per-app tuning.

If you find a gap (a state, a component class, an animation timing) not
covered here, propose an addition to this document via the vault-themes
repo so it becomes the single source of truth — don't fork the spec.
