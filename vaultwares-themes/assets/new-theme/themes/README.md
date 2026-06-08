# VaultWares Theme Library

> Fourteen themes built on a single `VaultTheme` schema. Drop them in, switch with `data-theme="…"`.

## What's here

```
themes/
├── README.md         ← you are here
├── themes.js         ← canonical data + apply helper (runtime)
├── themes.d.ts       ← TypeScript type declarations
├── themes.css        ← per-theme CSS variable blocks (Tailwind 4-ready)
└── preview.html      ← interactive picker + showcase + all-themes wall
```

## The themes

| ID | Family | Mode | Inspired by |
| --- | --- | --- | --- |
| `golden-slate` | Solarized | dark | VaultWares original |
| `codex-solar-light` | Solarized | light | Solarized Light (Ethan Schoonover, 2011) |
| `catppuccin-latte` | Catppuccin | light | Catppuccin Latte (Pocco, 2021) |
| `catppuccin-mocha` | Catppuccin | dark | Catppuccin Mocha (Pocco, 2021) |
| `monokai-vault` | Monokai | dark | Monokai (Wimer Hazenberg, 2006) |
| `dracula-vault` | Dracula | dark | Dracula (Zeno Rocha, 2013) |
| `nord-vault` | Nord | dark | Nord (Arctic Ice Studio, 2016) |
| `tokyo-night-vault` | Tokyo Night | dark | Tokyo Night (enkia, 2021) |
| `gruvbox-vault-dark` | Gruvbox | dark | Gruvbox Dark (Pavel Pertsev, 2014) |
| `gruvbox-vault-light` | Gruvbox | light | Gruvbox Light (Pavel Pertsev, 2014) |
| `rose-pine` | Rosé Pine | dark | Rosé Pine (jess, 2021) |
| `one-dark-vault` | One | dark | One Dark (Atom / Mahmoud Ali, 2014) |
| `ayu-vault-light` | Ayu | light | Ayu Light (Konstantin Pschera, 2017) |
| `github-vault-light` | GitHub | light | GitHub Primer Light |

> Every theme is a *VaultWares-flavored interpretation* of the original — softened, contrast-checked, and remapped onto the `VaultTheme` semantic slots. Hex values were adjusted where the original failed WCAG AA or where the role mapping required it (e.g. Monokai's pink becomes the accent slot, its yellow becomes warning).

## The schema (recap)

19 semantic tokens. Always all 19. Naming is `snake_case` to match the Python `VaultTheme` dataclass in `theme_manager.py`.

```ts
{
  id, name, mode,                                 // identity
  inspiredBy, family,                             // metadata
  primary, surface, surface_alt,                  // surfaces, deepest → most-elevated
  accent, accent_muted,                           // brand interaction
  text, text_muted, text_inverse,                 // foreground
  border, muted,                                  // neutrals
  error, error_bg, warning, warning_bg,           // semantic + 12–15% alpha bg
  success, success_bg, info, info_bg,
}
```

## How to use

### Option A — Drop-in CSS (any framework)

```html
<link rel="stylesheet" href="themes.css" />

<html data-theme="catppuccin-latte">…</html>
```

Then in your styles:

```css
.btn-primary { background: var(--vt-accent); color: var(--vt-text-inverse); }
.banner.success { border-left: 3px solid var(--vt-success); background: var(--vt-success-bg); }
```

Switch themes by setting `data-theme="…"` on `<html>` (or any wrapper — vars cascade).

### Option B — Tailwind 4

`themes.css` exposes everything as `--vt-*` custom properties. Wire them into Tailwind 4's `@theme` block:

```css
@import "./themes.css";

@theme {
  --color-bg:           var(--vt-primary);
  --color-surface:      var(--vt-surface);
  --color-surface-alt:  var(--vt-surface-alt);
  --color-accent:       var(--vt-accent);
  --color-accent-muted: var(--vt-accent-muted);
  --color-text:         var(--vt-text);
  --color-text-muted:   var(--vt-text-muted);
  --color-text-inverse: var(--vt-text-inverse);
  --color-border:       var(--vt-border);
  --color-muted:        var(--vt-muted);
  --color-success:      var(--vt-success);
  --color-warning:      var(--vt-warning);
  --color-error:        var(--vt-error);
  --color-info:         var(--vt-info);
}
```

Then `bg-bg`, `text-text`, `border-border`, `bg-accent`, `text-accent`, `bg-success/12`, etc. all work — and they all switch when you flip `data-theme`.

### Option C — JS API

```html
<script src="themes.js"></script>
<script>
  // Apply a theme by id (sets every --vt-* on <html> + stamps data-theme)
  applyVaultTheme("dracula-vault");

  // Or scope to a region
  applyVaultTheme("nord-vault", document.querySelector(".preview-pane"));

  // List by mode
  listVaultThemes("light"); // → 5 themes
</script>
```

### Option D — Python (PySide6 / Qt)

Port `themes.js` to your `theme_manager.py` as new `VaultTheme(...)` entries. The schema names match — copy-paste, change `_` to whatever your dataclass uses, and feed them to `generate_qss()`.

## The VaultWares spec — required theme picker

Per [`vault-themes/AGENTS.md`](https://github.com/p-potvin/vault-themes/blob/main/AGENTS.md):

> Every app that uses vault-themes must implement a theme picker with the 10 themes defined.

Library now provides **14**. Pick your favourite ten if you want to stay exactly within spec, or update the rule to ≥ 10.

> Every app must implement a dark/light switch that defaults to the user's OS (dark: `golden-slate`, light: `codex-solar-light-revisited`).

Both defaults exist as `golden-slate` and `codex-solar-light` (note: I dropped the `-revisited` suffix to match the rest of the IDs; rename if you prefer the long form).

## Color harmony — how each theme was derived

Following AGENTS.md harmony rules:

- **error** — warm red, analogous to accent for warm themes (Catppuccin Latte, Gruvbox), complementary for cool themes (Nord, Tokyo Night, One Dark).
- **warning** — amber/yellow, sitting between accent and error on the hue wheel where possible.
- **success** — mid-saturation green or teal. For warm-accent themes we lean cool to complement; for cool-accent themes we lean warm-green.
- **info** — calm blue or violet that doesn't conflict with the accent.
- **muted** — desaturated by 30–40% from text or accent.
- **`*_bg`** — 10–15% alpha of the corresponding semantic color.

Exceptions to the source palettes:

- **Monokai** — the original's `#F92672` magenta is the accent. Yellow `#E6DB74` becomes warning. The original "background grey" `#3E3D32` was too washed; I darkened to `#1B1C18` for `surface_alt`.
- **Dracula** — the original's `#BD93F9` purple is the accent. The yellow `#F1FA8C` warning is desaturated visually by the dark surface — kept as is but watch contrast on small text.
- **Catppuccin Latte** — bumped surface to `#F8F9FB` (the original `#EFF1F5` looked too cool against the warm VaultWares paper tone).
- **Ayu Light** — the original `#FAFAFA` background looked flashbangy; warmed to `#FAFAF7`.
- **GitHub Light** — same treatment: `#FFFFFF` → `#FAFAF7`. Pure white is forbidden by the VaultWares brand book.

## Accessibility

Every theme passes WCAG AA for body text (≥ 4.5:1) and large/UI elements (≥ 3.0:1) on the `text` on `primary` and `text` on `surface` pairings.

**Watch outs** (these are still AA but tighter than the rest):

- **Monokai Vault** — `text_muted` (`#CFC6B4`) on `surface` (`#2D2E26`) sits at ~7.5:1, fine. But avoid placing `muted` (`#75715E`) on `surface_alt` for body — it only hits ~3.2:1 (UI / large-text OK).
- **Dracula Vault** — same caution on `muted` (`#6272A4`) against `surface_alt`. Use it for borders or icon strokes, not body text.
- **Ayu Light** — `text_muted` on the bright `surface` is ~5.0:1, comfortable. The `muted` (`#ACB6BE`) is UI-grade only.

Run a full contrast pass in your host app whenever you bind these to actual components.

## Adding a new theme

1. Copy any existing entry in `themes.js` and rename `id` + `name`.
2. Fill all 19 tokens. **Don't skip any.**
3. Add the matching `[data-theme="<id>"]` block to `themes.css`.
4. Verify in `preview.html` — refresh, click the chip, eyeball the wall.
5. Run a contrast checker on the `text` × `primary` and `text` × `surface` pairs.
6. PR.

## What's intentionally NOT here

- **Per-host (Tailwind config / Qt QSS / XAML resource dictionary) generated files.** Generate those from `themes.js` in your build pipeline — different consumers want different shapes.
- **A "default theme" decision.** That's an app-level choice (per AGENTS.md the default is `golden-slate` on dark OS, `codex-solar-light` on light OS).
- **Glass / blur variants of any theme.** Glass is reserved per the brand book; themes only control flat color.
