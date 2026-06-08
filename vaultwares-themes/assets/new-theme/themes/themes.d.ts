/* VaultWares Theme Library — TypeScript type declarations
   --------------------------------------------------------------------------
   For consumers using TypeScript. Pair with `themes.js`:

       import "./themes.js"; // populates window.VAULT_THEMES
       declare global {
         interface Window {
           VAULT_THEMES: VaultTheme[];
           VAULT_THEME_BY_ID: Record<string, VaultTheme>;
           applyVaultTheme: (id: string, root?: HTMLElement) => VaultTheme | null;
           getVaultTheme: (id: string) => VaultTheme | undefined;
           listVaultThemes: (mode?: VaultMode) => VaultTheme[];
         }
       }

   Or, if you're regenerating tokens from scratch in a Tailwind/Vite app, port
   themes.js to themes.ts with `as const` for full type narrowing.
   ------------------------------------------------------------------------- */

export type VaultMode = "light" | "dark";

export type VaultThemeFamily =
  | "Solarized"
  | "Catppuccin"
  | "Monokai"
  | "Dracula"
  | "Nord"
  | "Tokyo Night"
  | "Gruvbox"
  | "Rosé Pine"
  | "One"
  | "Ayu"
  | "GitHub";

export interface VaultTheme {
  /** Machine identifier (kebab-case). */
  id: string;
  /** Display name (Title Case). */
  name: string;
  mode: VaultMode;
  /** Free-text attribution. */
  inspiredBy: string;
  /** Theme family for grouping in the picker. */
  family: VaultThemeFamily;

  primary: string;
  surface: string;
  surface_alt: string;

  accent: string;
  accent_muted: string;

  text: string;
  text_muted: string;
  text_inverse: string;

  border: string;
  muted: string;

  error: string;
  error_bg: string;
  warning: string;
  warning_bg: string;
  success: string;
  success_bg: string;
  info: string;
  info_bg: string;
}

export declare const VAULT_THEMES: readonly VaultTheme[];
export declare const VAULT_THEME_BY_ID: Readonly<Record<string, VaultTheme>>;

/** Apply a theme by setting `--vt-*` CSS variables on `root` (default `<html>`). */
export declare function applyVaultTheme(
  id: string,
  root?: HTMLElement,
): VaultTheme | null;

export declare function getVaultTheme(id: string): VaultTheme | undefined;
export declare function listVaultThemes(mode?: VaultMode): VaultTheme[];
