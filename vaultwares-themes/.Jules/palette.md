## 2026-05-05 - VaultCoreBadge Accessibility and UX Improvements
**Learning:** Adding a native HTML title attribute and cursor: help is a simple, lightweight way to add tooltip-like hints without needing heavy components. And role="status" + aria-label ensures screen readers get the context they need for important status badges.
**Action:** Use this simple pattern for status badges instead of heavier tooltip wrappers when only simple text explanation is needed.
## 2026-05-06 - VaultCoreBadge Accessibility and UX Improvements
**Learning:** Adding a native HTML title attribute and cursor: help is a simple, lightweight way to add tooltip-like hints without needing heavy components. And role="status" + aria-label ensures screen readers get the context they need for important status badges.
**Action:** Use this simple pattern for status badges instead of heavier tooltip wrappers when only simple text explanation is needed.

## 2026-05-07 - Brand Guide Token Swatch Copy-to-Clipboard Enhancement
**Learning:** When displaying reference data like hex color codes in a brand guide or style dictionary, users frequently need to copy them. Providing a one-click copy mechanism wrapped in a semantic `<button>` with clear focus states (`focus-visible:ring-2`) and aria-labels improves workflow efficiency and keyboard accessibility significantly compared to static text.
**Action:** When creating visual reference UI (swatches, tokens, IDs), always consider adding an inline copy action with visual and screen-reader accessible feedback (e.g., swapping a copy icon to a check icon temporarily).
## 2026-05-08 - Brand Guide Token Swatch Copy-to-Clipboard Enhancement (Focus & Screen Reader)
**Learning:** While wrapping token copy actions in a `<button>` with clear focus states and aria-labels is great, the visual feedback needs to accommodate all interactive states, and screen readers need explicit feedback when visually silent background actions (like copying) complete.
**Action:** When a hover-revealed icon indicates interactivity (like a copy icon), ensure it is also revealed on keyboard focus (e.g. `group-focus-visible:opacity-100`). Always pair background copy actions with a visually hidden `aria-live="polite"` region that announces the successful outcome.

## 2026-05-13 - Comparison Table Accessibility
**Learning:** Comparison tables (like "Avoid vs Use") shouldn't rely solely on color to indicate meaning (e.g. red for avoid, green for use). Additionally, when icons are used for visual queues, screen readers need explicit visually hidden labels (`sr-only`) to give context to the list items, otherwise it's just a series of disconnected strings.
**Action:** Always include an icon for both positive and negative states. Use `sr-only` spans to provide explicit textual context (like "Avoid:" or "Use:") next to visual queues in comparison list items.
## 2025-01-20 - Screen Reader Context for Color-Coded Tables
**Learning:** Tables that use purely visual or color-based cues (like a Voice Replacement table using burgundy text vs. a green checkmark to indicate "do/don't") fail to provide context to screen reader users.
**Action:** Always prepend visually hidden text (`<span className="sr-only">Avoid saying: </span>`, `<span className="sr-only">Instead use: </span>`) to the content to ensure the meaning is semantically clear without relying on visual style.
