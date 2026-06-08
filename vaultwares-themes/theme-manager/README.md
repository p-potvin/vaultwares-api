# vault-themes / theme-manager

The **theme-manager** directory is the canonical distribution point for VaultWares
design tokens across every language and platform that VaultWares products target.

---

## Contents

```text
theme-manager/
├── exports/               # Ready-to-import files for each platform
│   ├── theme-manager.ts   # TypeScript/JavaScript — full VaultTheme catalog
│   ├── vault-tailwind-v4.css  # Tailwind CSS v4 theme bridge  ← NEW
│   ├── theme-manager.tw   # Tailwind CSS v3 config extension
│   ├── theme_manager.py   # Python — PySide6/Qt QSS + dataclass
│   ├── qt_exporter.py     # Python — Qt stylesheet generator
│   ├── themeManager.cs    # C#/.NET — WinUI 3, WPF, MAUI
│   └── VaultWares.Brand.xaml  # WPF/WinUI XAML ResourceDictionary
├── python/                # Python package (importable)
│   └── __init__.py
└── tools/
    └── sync_submodule_rules.py
```

---

## How to import — by language / platform

### 1. TypeScript / JavaScript (Vite, Next.js, any bundler)

```ts
// Option A — direct import (vault-themes is a sibling/submodule)
import { THEMES, VaultThemeManager } from "../vault-themes/theme-manager/exports/theme-manager";

// Option B — if you copy or symlink the file
import { THEMES, VaultThemeManager } from "./theme-manager";

// Usage
const manager = new VaultThemeManager();
const theme = manager.getTheme("Golden Slate"); // by name
const default_ = manager.getTheme(undefined, 0); // by index
```

**Inject tokens at runtime (required for CSS utilities to work):**

```ts
function applyTheme(theme: VaultTheme) {
    const root = document.documentElement;
    Object.entries(theme).forEach(([key, value]) => {
        if (!["name", "id", "mode"].includes(key)) {
            root.style.setProperty(`--${key.replaceAll("_", "-")}`, value);
        }
    });
    root.setAttribute("data-mode", theme.mode);
    // Persist across sessions
    localStorage.setItem("vw-theme-id", theme.id);
    localStorage.setItem("vw-theme-mode", theme.mode);
}
```

---

### 2. Tailwind CSS v4 (Vite + `@tailwindcss/vite` or PostCSS)

Add **one** import in your project's main CSS file (e.g. `src/index.css`):

```css
@import "tailwindcss";
@import "../vault-themes/theme-manager/exports/vault-tailwind-v4.css";
```

This gives you utilities like `bg-background`, `text-text-primary`, `border-border`,
`bg-accent`, `text-accent-muted`, `bg-error-bg`, etc.

You still need to inject the CSS custom properties at runtime with the TypeScript
snippet above — the bridge only maps existing `--tokens` to Tailwind class names.

---

### 3. Tailwind CSS v3 (legacy)

```js
// tailwind.config.js
const vaultExtend = require("./vault-themes/theme-manager/exports/theme-manager.tw");

module.exports = {
    content: ["./src/**/*.{html,js,ts,jsx,tsx}"],
    theme: {
        extend: {
            colors: vaultExtend.theme.extend.colors
        }
    }
};
```

> Note: v3 uses static hardcoded values (Golden Slate defaults). For
> runtime-switchable multi-theme support, prefer the v4 CSS bridge.

---

### 4. Python — PySide6 / Qt (QSS stylesheets)

```python
# Option A — add vault-themes to sys.path
import sys
sys.path.insert(0, '/path/to/vault-themes')
from theme_manager import THEMES, get_theme   # root-level convenience re-export

# Option B — import directly from the exports file
sys.path.insert(0, '/path/to/vault-themes/theme-manager/exports')
from theme_manager import THEMES, VaultThemeManager, generate_qss

# Usage
manager = VaultThemeManager()
theme   = manager.get_theme('Golden Slate')
qss     = generate_qss(theme)
app.setStyleSheet(qss)
```

The `theme_manager.py` also exports a `VaultTheme` dataclass with all 19 tokens
as attributes (snake_case). See `qt_exporter.py` for the full QSS generator.

---

### 5. Python — Package import (if installed as editable package)

```python
# If vault-themes is installed with:  pip install -e .
from vault_themes import THEMES, VaultThemeManager
```

The `theme-manager/python/__init__.py` re-exports the public API.

---

### 6. C# — .NET (WinUI 3, WPF, MAUI, Avalonia)

```csharp
// Copy themeManager.cs into your project under VaultWares.Themes namespace
// or reference via a shared class library project.

using VaultWares.Themes;

var theme   = ThemeManager.GetTheme("Golden Slate");
var darkBg  = theme.Background;     // "#2E3538"
var accent  = theme.Accent;         // "#D4AF37"
var surface = theme.Surface;        // "#363D41"
```

For WPF / WinUI XAML ResourceDictionary injection:

```xml
<!-- App.xaml -->
<Application.Resources>
  <ResourceDictionary>
    <ResourceDictionary.MergedDictionaries>
      <ResourceDictionary Source="Themes/VaultWares.Brand.xaml" />
    </ResourceDictionary.MergedDictionaries>
  </ResourceDictionary>
</Application.Resources>
```

---

### 7. WPF / WinUI — XAML Resource Dictionary only

```xml
<!-- Any XAML file -->
<ResourceDictionary Source="pack://application:,,,/YourAssembly;component/Themes/VaultWares.Brand.xaml" />

<!-- Usage -->
<TextBlock Foreground="{StaticResource VaultGoldBrush}" />
<Border Background="{ThemeResource ApplicationPageBackgroundThemeBrush}" />
```

---

## Theme Defaults

| Theme                     | Mode  | Default?         |
| ------------------------- | ----- | ---------------- |
| Golden Slate              | dark  | ✅ dark default  |
| Solarized Light Revisited | light | ✅ light default |
| Cyberpunk Cinder          | dark  | —                |
| Vintage Velvet            | light | —                |
| … (15 total)              | —     | —                |

Per `AGENTS.md`: always default to **Golden Slate** (dark) and **Solarized Light Revisited** (light).
Both must respect the user's OS `prefers-color-scheme` on first visit.

---

## Token Reference

Every theme must define all 19 semantic tokens:

| Token                    | Role                              |
| ------------------------ | --------------------------------- |
| `background`             | Root page / window background     |
| `surface`                | Panel / card background           |
| `surface_alt`            | Nested element background         |
| `surface_elevated`       | Overlay / elevated surface        |
| `text`                   | Alias for `text_primary`          |
| `text_primary`           | Primary body text                 |
| `text_secondary`         | Captions, secondary labels        |
| `text_muted`             | Tertiary / placeholder text       |
| `text_inverse`           | Text on accent-colored surfaces   |
| `accent`                 | Brand accent, primary interactive |
| `accent_muted`           | Hover / pressed accent            |
| `border`                 | Subtle panel / input borders      |
| `error` / `error_bg`     | Error / destructive state + bg    |
| `warning` / `warning_bg` | Warning / caution state + bg      |
| `success` / `success_bg` | Success / secured state + bg      |
| `info` / `info_bg`       | Informational state + bg          |
| `muted`                  | Disabled / muted elements         |

`*_bg` values must use **rgba with 12–15% alpha** for readability.

---

## Adding a New Theme

1. Add the theme object to **all** platform files simultaneously to keep them in sync:
    - `exports/theme-manager.ts`
    - `exports/theme_manager.py`
    - `exports/themeManager.cs`
2. Follow the color harmony rules in `AGENTS.md` § "Color harmony rules".
3. Run the contrast check: body text vs background must pass **WCAG AA (4.5:1)**.
4. Add the theme name to `brand/i18n/brand.i18n.ts` in both EN and QC.

---

## Missing-Language Policy

If your target language / platform does not have a theme manager file yet, create one
in `vault-themes/theme-manager/exports/` following the naming convention:

```text
theme-manager.<ext>    e.g. theme-manager.dart, theme-manager.swift, theme-manager.kt
```

Then update this README and the AGENTS.md with import instructions.

**Currently supported:**

| Language / Platform | File                                  | Notes                            |
| ------------------- | ------------------------------------- | -------------------------------- |
| TypeScript / JS     | `theme-manager.ts`                    | Universal — works in any bundler |
| Tailwind CSS v4     | `vault-tailwind-v4.css`               | CSS-only bridge                  |
| Tailwind CSS v3     | `theme-manager.tw`                    | Static config extend             |
| Python / Qt         | `theme_manager.py` + `qt_exporter.py` | PySide6 QSS                      |
| C# / .NET           | `themeManager.cs`                     | WinUI 3, WPF, MAUI               |
| WPF / WinUI XAML    | `VaultWares.Brand.xaml`               | ResourceDictionary               |

**Planned / community contributed:**

| Language                 | File (proposed)      | Status  |
| ------------------------ | -------------------- | ------- |
| Dart / Flutter           | `theme-manager.dart` | Planned |
| Swift / SwiftUI          | `VaultTheme.swift`   | Planned |
| Kotlin / Jetpack Compose | `VaultTheme.kt`      | Planned |
| CSS-only (no framework)  | `vault-tokens.css`   | Planned |
