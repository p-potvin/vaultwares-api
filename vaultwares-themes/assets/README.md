# VaultWares Assets

Assets are grouped by purpose.

| Folder | Contents |
| --- | --- |
| `logos/` | Wordmarks, minimal marks, SVG/PNG logo variants. |
| `icons/` | React icon snippets and small UI icons. |
| `favicons/` | PNG favicon exports by color and size. |
| `source/` | Source design files such as PSDs. |

## Logo Guidance

- Prefer `assets/logos/vaultwares-logo.png` for the current full-color rendered
  guide/demo logo.
- Use SVG variants when a project needs scalable mono/dark assets.
- Keep minimal marks for favicons, extension icons, and compact UI only.
- Do not recolor the standard mark without updating the brand guide.

## Maintenance

Generated image exports should be replaceable from source assets. Keep generated
files named by purpose, color, and size. Do not place generated HTML bundles or
runtime JavaScript in `assets/`.
