from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class VaultTheme:
    """
    Full semantic color token set for a VaultWares theme.

    Tokens
    ------
    name        : User-facing display name (Title Case).
    mode        : "light" or "dark".
    primary     : Main window background color.
    surface     : Panel / card background (slightly offset from primary).
    surface_alt : Secondary surface for nested elements.
    accent      : Brand accent — primary interactive color.
    accent_muted: A 60%-opacity or desaturated version of the accent.
    text        : Primary body text color.
    text_muted  : Secondary / caption text color.
    text_inverse: Text on accent-colored surfaces.
    border      : Subtle border color for panels and inputs.
    error       : Semantic error / destructive state color.
    error_bg    : Translucent background for error banners.
    warning     : Semantic warning / caution state color.
    warning_bg  : Translucent background for warning banners.
    success     : Semantic success / positive state color.
    success_bg  : Translucent background for success banners.
    info        : Semantic informational state color.
    info_bg     : Translucent background for info banners.
    muted       : Muted/disabled UI elements and placeholder text.
    """
    name: str
    mode: str                # "light" | "dark"
    primary: str             # legacy alias for background (back-compat)
    background: str          # Main window background
    surface: str             # Panel / card background
    surface_alt: str         # Secondary surface
    surface_elevated: str    # Elevated surface (e.g. hovered cards)
    text_primary: str        # Main text
    text_secondary: str      # Secondary text
    accent: str              # Brand accent
    accent_muted: str
    text: str
    text_muted: str
    text_inverse: str
    border: str
    error: str
    error_bg: str
    warning: str
    warning_bg: str
    success: str
    success_bg: str
    info: str
    info_bg: str
    muted: str


class VaultThemeManager:
    """
    Centralized theme manager for VaultWares projects.
    Handles theme definitions, color extraction, and glass-ui style generation.

    All colors are derived from VaultWares brand tokens (Brand/tokens.ts) and
    per-theme complementary/analogous palettes designed for WCAG AA compliance.
    """

    def __init__(self):
        self._themes = [
            # ── Golden Slate (DARK) — flagship dark theme ──────────────────
            # Accent: warm gold. Complementary: deep teal blue.
            # Error: terracotta-red (analogous to gold). Success: muted olive-green.
            VaultTheme(
                name="Golden Slate",
                mode="dark",
                primary="#2E3538",
                background="#2E3538",
                surface="#363D41",
                surface_alt="#3F474C",
                surface_elevated="#485157",
                text_primary="#EDE8DE",
                text_secondary="#B8B1A5",
                accent="#D4AF37",
                accent_muted="#A8892A",
                text="#EDE8DE",
                text_muted="#8FA0A8",
                text_inverse="#1C2226",
                border="rgba(212,175,55,1)",
                error="#E05C4A",        # terracotta — warm, fits gold palette
                error_bg="rgba(224,92,74,0.14)",
                warning="#E09D34",      # amber — analogous to gold
                warning_bg="rgba(224,157,52,0.14)",
                success="#5BAD72",      # sage green — complementary to burgundy
                success_bg="rgba(91,173,114,0.14)",
                info="#5B9FBF",         # steel blue — cool offset to warm gold
                info_bg="rgba(91,159,191,0.14)",
                muted="#586672",
            ),

            # ── Codex Solarized Light Revisited (LIGHT) ────────────────────
            # Classic Solarized. Accent: deep cyan-blue. Error: red-orange.
            VaultTheme(
                name="Codex Solarized Light Revisited",
                mode="light",
                primary="#FDF6E3",
                background="#FDF6E3",
                surface="#F5EFD6",
                surface_alt="#EDE5C8",
                surface_elevated="#E6DDBA",
                text_primary="#073642",
                text_secondary="#586E75",
                accent="#268BD2",
                accent_muted="#1A6BA8",
                text="#073642",
                text_muted="#657B83",
                text_inverse="#FDF6E3",
                border="rgba(38,139,210,0.2)",
                error="#DC322F",        # solarized red — canonical
                error_bg="rgba(220,50,47,0.1)",
                warning="#CB4B16",      # solarized orange
                warning_bg="rgba(203,75,22,0.1)",
                success="#859900",      # solarized green
                success_bg="rgba(133,153,0,0.1)",
                info="#2AA198",         # solarized cyan
                info_bg="rgba(42,161,152,0.1)",
                muted="#93A1A1",
            ),

            # ── Cyberpunk Cinder (DARK) ────────────────────────────────────
            # Accent: burnt orange. Error: neon magenta. Success: acid green.
            VaultTheme(
                name="Cyberpunk Cinder",
                mode="dark",
                primary="#0A1520",
                background="#0A1520",
                surface="#0F1E2E",
                surface_alt="#162537",
                surface_elevated="#1D2E42",
                text_primary="#D4CFCF",
                text_secondary="#A0AAB2",
                accent="#CB4B16",
                accent_muted="#9A3A12",
                text="#D4CFCF",
                text_muted="#587080",
                text_inverse="#F0EBE0",
                border="rgba(203,75,22,0.22)",
                error="#FF2A6D",        # neon magenta-pink — cyberpunk danger
                error_bg="rgba(255,42,109,0.12)",
                warning="#FF9F1C",      # neon amber
                warning_bg="rgba(255,159,28,0.12)",
                success="#05E988",      # acid green — classic cyber
                success_bg="rgba(5,233,136,0.12)",
                info="#00B4D8",         # electric cyan
                info_bg="rgba(0,180,216,0.12)",
                muted="#3D5060",
            ),

            # ── Vintage Velvet (LIGHT) ─────────────────────────────────────
            # Accent: deep burgundy. Error: crimson. Success: forest green.
            VaultTheme(
                name="Vintage Velvet",
                mode="light",
                primary="#F5F0E8",
                background="#F5F0E8",
                surface="#EDE7D9",
                surface_alt="#E2DAC9",
                surface_elevated="#D8CDB8",
                text_primary="#2C1810",
                text_secondary="#5A4A42",
                accent="#800020",
                accent_muted="#5E0018",
                text="#2C1810",
                text_muted="#7D6E62",
                text_inverse="#F5F0E8",
                border="rgba(128,0,32,0.2)",
                error="#B22222",        # firebrick — heavier than crimson, vintage
                error_bg="rgba(178,34,34,0.1)",
                warning="#C47D0E",      # antique gold
                warning_bg="rgba(196,125,14,0.1)",
                success="#2E6B4F",      # forest green
                success_bg="rgba(46,107,79,0.1)",
                info="#2C5F8A",         # Prussian blue — period-accurate
                info_bg="rgba(44,95,138,0.1)",
                muted="#9E8E82",
            ),

            # ── Modern Monolith (LIGHT) ────────────────────────────────────
            # Accent: near-black. Clean, editorial. Error: vivid red.
            VaultTheme(
                name="Modern Monolith",
                mode="light",
                primary="#F8F7F4",
                background="#F8F7F4",
                surface="#EFEDE8",
                surface_alt="#E5E2DC",
                surface_elevated="#DBD8D0",
                text_primary="#111111",
                text_secondary="#444444",
                accent="#1A1A1A",
                accent_muted="#444444",
                text="#111111",
                text_muted="#888888",
                text_inverse="#F8F7F4",
                border="rgba(26,26,26,0.14)",
                error="#C0392B",        # muted vivid red
                error_bg="rgba(192,57,43,0.09)",
                warning="#D4892A",      # warm amber
                warning_bg="rgba(212,137,42,0.09)",
                success="#27AE60",      # medium emerald
                success_bg="rgba(39,174,96,0.09)",
                info="#2980B9",         # modern blue
                info_bg="rgba(41,128,185,0.09)",
                muted="#AAAAAA",
            ),

            # ── Neon Void (DARK) ───────────────────────────────────────────
            # Accent: electric cyan. Error: hot magenta. Success: lime.
            VaultTheme(
                name="Neon Void",
                mode="dark",
                primary="#0D0D0D",
                background="#0D0D0D",
                surface="#141414",
                surface_alt="#1C1C1C",
                surface_elevated="#252525",
                text_primary="#E8E8E8",
                text_secondary="#B0B0B0",
                accent="#00E5FF",
                accent_muted="#008FA8",
                text="#E8E8E8",
                text_muted="#606060",
                text_inverse="#0D0D0D",
                border="rgba(0,229,255,0.2)",
                error="#FF00AA",        # hot magenta — neon danger
                error_bg="rgba(255,0,170,0.12)",
                warning="#FFDD00",      # electric yellow
                warning_bg="rgba(255,221,0,0.12)",
                success="#39FF14",      # neon lime
                success_bg="rgba(57,255,20,0.12)",
                info="#BD00FF",         # electric violet
                info_bg="rgba(189,0,255,0.12)",
                muted="#383838",
            ),

            # ── Ocean Mist (LIGHT) ─────────────────────────────────────────
            # Accent: deep ocean blue. Error: coral. Success: teal.
            VaultTheme(
                name="Ocean Mist",
                mode="light",
                primary="#EEF2F5",
                background="#EEF2F5",
                surface="#E3EAEF",
                surface_alt="#D6E0E8",
                surface_elevated="#C9D6DF",
                text_primary="#1A2A35",
                text_secondary="#4A5A65",
                accent="#006994",
                accent_muted="#004F6E",
                text="#1A2A35",
                text_muted="#708090",
                text_inverse="#FFFFFF",
                border="rgba(0,105,148,0.18)",
                error="#CD5C5C",        # indian red/coral — warm vs cool
                error_bg="rgba(205,92,92,0.1)",
                warning="#C4822A",      # sandy amber
                warning_bg="rgba(196,130,42,0.1)",
                success="#20B2AA",      # light sea green — analogous to ocean
                success_bg="rgba(32,178,170,0.1)",
                info="#4682B4",         # steel blue
                info_bg="rgba(70,130,180,0.1)",
                muted="#8FA0AA",
            ),

            # ── Royal Tangerine (DARK) ─────────────────────────────────────
            # Accent: vivid tangerine on deep indigo. Error: vermilion. Success: spring green.
            VaultTheme(
                name="Royal Tangerine",
                mode="dark",
                primary="#1A0A2E",
                background="#1A0A2E",
                surface="#231240",
                surface_alt="#2C1850",
                surface_elevated="#361F62",
                text_primary="#EEE8F8",
                text_secondary="#B8B0D0",
                accent="#F28500",
                accent_muted="#B86500",
                text="#EEE8F8",
                text_muted="#7A6A9A",
                text_inverse="#1A0A2E",
                border="rgba(242,133,0,0.2)",
                error="#FF4500",        # vermilion-red (warm, analogous to orange)
                error_bg="rgba(255,69,0,0.13)",
                warning="#FFB700",      # golden amber — adjacent to tangerine
                warning_bg="rgba(255,183,0,0.13)",
                success="#00E676",      # spring green — complementary to indigo
                success_bg="rgba(0,230,118,0.13)",
                info="#7B61FF",         # electric violet — analogous to indigo bg
                info_bg="rgba(123,97,255,0.13)",
                muted="#4A3A6A",
            ),

            # ── Crimson Bloom (DARK) ───────────────────────────────────────
            # Accent: dusty rose / blush on dark crimson. Error: bright red. Success: mint.
            VaultTheme(
                name="Crimson Bloom",
                mode="dark",
                primary="#2A0A0A",
                background="#2A0A0A",
                surface="#361212",
                surface_alt="#421818",
                surface_elevated="#4E1F1F",
                text_primary="#F5E8EA",
                text_secondary="#C5B8BA",
                accent="#E8A0B4",
                accent_muted="#B07086",
                text="#F5E8EA",
                text_muted="#9A7A82",
                text_inverse="#2A0A0A",
                border="rgba(232,160,180,0.2)",
                error="#FF4444",        # bright red on dark crimson — high contrast
                error_bg="rgba(255,68,68,0.14)",
                warning="#E8A030",      # amber — warm contrast to rose
                warning_bg="rgba(232,160,48,0.14)",
                success="#48D090",      # mint green — complementary contrast
                success_bg="rgba(72,208,144,0.14)",
                info="#90A8E8",         # periwinkle — cool offset
                info_bg="rgba(144,168,232,0.14)",
                muted="#5A3A3E",
            ),

            # ── Amethyst Frost (LIGHT) ─────────────────────────────────────
            VaultTheme(
                name="Amethyst Frost",
                mode="light",
                primary="#FAFAFE",
                background="#FAFAFE",
                surface="#F0EEF8",
                surface_alt="#E4E0F4",
                surface_elevated="#D8D2F0",
                text_primary="#1A0A2E",
                text_secondary="#4A3A6A",
                accent="#6B30A8",
                accent_muted="#4E2280",
                text="#1A0A2E",
                text_muted="#7A6A9A",
                text_inverse="#FAFAFE",
                border="rgba(107,48,168,0.18)",
                error="#C2185B",
                error_bg="rgba(194,24,91,0.09)",
                warning="#E67E22",
                warning_bg="rgba(230,126,34,0.09)",
                success="#388E3C",
                success_bg="rgba(56,142,60,0.09)",
                info="#0288D1",
                info_bg="rgba(2,136,209,0.09)",
                muted="#C0B8D8",
            ),

            # ── Catppuccin Mocha (DARK) ────────────────────────────────────
            VaultTheme(
                name="Catppuccin Mocha",
                mode="dark",
                primary="#1E1E2E",
                background="#1E1E2E",
                surface="#181825",
                surface_alt="#11111B",
                surface_elevated="#313244",
                text_primary="#CDD6F4",
                text_secondary="#A6ADC8",
                accent="#CBA6F7", # mauve
                accent_muted="#957FB8",
                text="#CDD6F4",
                text_muted="#6C7086",
                text_inverse="#11111B",
                border="rgba(203,166,247,0.2)",
                error="#F38BA8", # red
                error_bg="rgba(243,139,168,0.1)",
                warning="#FAB387", # peach
                warning_bg="rgba(250,179,135,0.1)",
                success="#A6E3A1", # green
                success_bg="rgba(166,227,161,0.1)",
                info="#89B4FA", # blue
                info_bg="rgba(137,180,250,0.1)",
                muted="#45475A",
            ),

            # ── Dracula (DARK) ─────────────────────────────────────────────
            VaultTheme(
                name="Dracula",
                mode="dark",
                primary="#282A36",
                background="#282A36",
                surface="#343746",
                surface_alt="#44475A",
                surface_elevated="#6272A4",
                text_primary="#F8F8F2",
                text_secondary="#BD93F9",
                accent="#FF79C6",
                accent_muted="#D163A3",
                text="#F8F8F2",
                text_muted="#6272A4",
                text_inverse="#282A36",
                border="rgba(189,147,249,0.2)",
                error="#FF5555",
                error_bg="rgba(255,85,85,0.1)",
                warning="#F1FA8C",
                warning_bg="rgba(241,250,140,0.1)",
                success="#50FA7B",
                success_bg="rgba(80,250,123,0.1)",
                info="#8BE9FD",
                info_bg="rgba(139,233,253,0.1)",
                muted="#44475A",
            ),

            # ── Tokyo Night Storm (DARK) ───────────────────────────────────
            VaultTheme(
                name="Tokyo Night Storm",
                mode="dark",
                primary="#24283B",
                background="#24283B",
                surface="#1F2335",
                surface_alt="#1A1B26",
                surface_elevated="#292E42",
                text_primary="#A9B1D6",
                text_secondary="#9ECE6A",
                accent="#7AA2F7",
                accent_muted="#5B7CC4",
                text="#A9B1D6",
                text_muted="#565F89",
                text_inverse="#1A1B26",
                border="rgba(122,162,247,0.2)",
                error="#F7768E",
                error_bg="rgba(247,118,142,0.1)",
                warning="#E0AF68",
                warning_bg="rgba(224,175,104,0.1)",
                success="#73DACA",
                success_bg="rgba(115,218,202,0.1)",
                info="#B4F9F8",
                info_bg="rgba(180,249,248,0.1)",
                muted="#32344A",
            ),

            # ── GitHub Light Default (LIGHT) ───────────────────────────────
            VaultTheme(
                name="GitHub Light Default",
                mode="light",
                primary="#FFFFFF",
                background="#FFFFFF",
                surface="#F6F8FA",
                surface_alt="#EAEFEF",
                surface_elevated="#D0D7DE",
                text_primary="#1F2328",
                text_secondary="#65717E",
                accent="#0969DA",
                accent_muted="#0550AE",
                text="#1F2328",
                text_muted="#6E7781",
                text_inverse="#FFFFFF",
                border="rgba(31,35,40,0.15)",
                error="#D1242F",
                error_bg="rgba(209,36,47,0.1)",
                warning="#9A6700",
                warning_bg="rgba(154,103,0,0.1)",
                success="#1A7F37",
                success_bg="rgba(26,127,55,0.1)",
                info="#0969DA",
                info_bg="rgba(9,105,218,0.1)",
                muted="#AFB8C1",
            ),

            # ── Monokai Pro (DARK) ─────────────────────────────────────────
            VaultTheme(
                name="Monokai Pro",
                mode="dark",
                primary="#2D2A2E",
                background="#2D2A2E",
                surface="#37343A",
                surface_alt="#221F22",
                surface_elevated="#403E41",
                text_primary="#FCFCFA",
                text_secondary="#A9DC76",
                accent="#FFD866",
                accent_muted="#C9AB51",
                text="#FCFCFA",
                text_muted="#727072",
                text_inverse="#2D2A2E",
                border="rgba(255,216,102,0.2)",
                error="#FF6188",
                error_bg="rgba(255,97,136,0.1)",
                warning="#FC9867",
                warning_bg="rgba(252,152,103,0.1)",
                success="#A9DC76",
                success_bg="rgba(169,220,118,0.1)",
                info="#78DCE8",
                info_bg="rgba(120,220,232,0.1)",
                muted="#5B595C",
            ),
        ]

    def get_themes(self) -> List[VaultTheme]:
        return self._themes

    def get_theme(self, name: str = None, index: int = 0) -> VaultTheme:
        if name:
            for t in self._themes:
                if t.name == name:
                    return t
        if 0 <= index < len(self._themes):
            return self._themes[index]
        return self._themes[0]

    def get_theme_by_name(self, name: str) -> VaultTheme:
        for theme in self._themes:
            if theme.name == name:
                return theme
        return self._themes[0]


    @staticmethod
    def hex_to_rgba(hex_color: str, alpha: float) -> str:
        """Converts hex to rgba for glass-ui elements. Alpha in 0.0–1.0."""
        hex_color = hex_color.lstrip('#')
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return f"rgba({r}, {g}, {b}, {alpha})"

    # Legacy alias
    @staticmethod
    def get_glass_rgba(hex_color: str, alpha: int) -> str:
        return VaultThemeManager.hex_to_rgba(hex_color, alpha / 255)
