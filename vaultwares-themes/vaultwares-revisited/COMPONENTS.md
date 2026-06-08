# VaultWares Revisited: Components & Layout

This document outlines standard primitives used across the VaultWares-Revisited design framework.

## 1. Shells & Backgrounds

Shells control the primary background rendering, including subtle ambient glows to provide depth.

- **`.vw-console-shell`**
  Used as the root class for Console mode.
  Applies a `radial-gradient` (a subtle violet glow originating from the top) fading into `--vault-console-bg`.

- **`.vw-warm-shell`**
  Used as the root class for Warm mode.
  Applies a subtle golden `radial-gradient` fading into the `--vault-warm-bg` parchment tone.

## 2. Cards & Containers

Cards are transparent, glossy, and use specific compositing techniques.

- **`.vw-card` (Console Card)**
  - Border: `1px solid var(--vault-console-border-subtle)`
  - Background: `color-mix(in srgb, var(--vault-console-raised) 86%, transparent)` (Slightly transparent for depth)
  - Border-Radius: `28px` (High radius for a modern smooth feel)

- **`.vw-warm-card` (Warm Card)**
  - Border: `1px solid var(--vault-warm-border-subtle)`
  - Background: `var(--vault-warm-raised)`
  - Border-Radius: `28px`

## 3. Indicators (LEDs)

To simulate hardware, "LED" elements are used to denote active states, connection statuses, or live syncs.

- **`.vw-led`**
  Provides a very slow and subtle rhythmic hardware pulse.

  ```css
  @keyframes ledPulse {
    0% { opacity: 0.85; transform: scale(0.98); }
    50% { opacity: 1; transform: scale(1); }
    100% { opacity: 0.85; transform: scale(0.98); }
  }
  ```

  *(Animation duration should be around 4s or longer to ensure subtlety)*

## 4. Scrollbars (Console specific)

In Console Mode, native scrollbars are restyled to look like sleek terminal tracks:

- Track: `#000`
- Thumb: `--vault-console-raised` (Hover: `--vault-console-gold`)
