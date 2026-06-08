## 2026-05-10 - Comparison Table Accessibility Enhancement
- **Agent**: Palette 🎨
- **Project**: vault-themes (brand-guide-demo)
- **Change**: Added X icons and visually hidden labels to the voice replacement table in App.tsx.
- **Reasoning**: Comparison tables shouldn't rely solely on color to indicate meaning. Screen readers also need context for visual queues.
- **Impact**: Improved accessibility and visual scannability for all users.

### Context
User requested a micro-UX improvement focusing on accessibility and intuitive interaction, acting as "Palette". Explored the `examples/brand-guide` react application.

### Decisions & Changes
- Added `aria-hidden="true"` to purely decorative Lucide icons (`<ShieldCheck>`, `<Icon>`, `<Copy>`, `<Check>`) in `App.tsx` to prevent screen readers from announcing them redundantly.
- Changed the hardcoded numbered list in "Brand priorities" to use Tailwind's native semantic `list-decimal` (`list-decimal list-inside`), removing manual numbers ("1. ", "2. ") from the list items.
- Added visually hidden context (`<span className="sr-only">Avoid saying: </span>`, `<span className="sr-only">Instead use: </span>`) to the "Voice replacement table". Previously, this table relied purely on color (burgundy text vs. a green checkmark) to indicate instructions, which was inaccessible.
- Enhanced the `title` attribute on the copy button to provide dynamic tooltip feedback ("Copied!" vs "Click to copy hex code") upon interaction.
- Verified build and syntax integrity via `pnpm build` in the `examples/brand-guide` submodule.
- Added a critical learning entry to `.Jules/palette.md` noting the importance of `sr-only` context for color-coded tables.

### Goal
To ensure the demo application strictly adheres to the WCAG guidelines implicitly required by the VaultWares philosophy, explicitly improving keyboard accessibility and screen reader support without changing existing design tokens.
