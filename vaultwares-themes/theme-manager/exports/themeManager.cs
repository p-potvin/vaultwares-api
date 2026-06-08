using System;
using System.Collections.Generic;
using System.Linq;

namespace VaultWares.Themes
{
    public class VaultTheme
    {
        public string Name { get; set; }
        public string Id { get; set; }
        public string Mode { get; set; } // "light" | "dark"
        public string Background { get; set; }
        public string Primary { get; set; }
        public string Surface { get; set; }
        public string SurfaceAlt { get; set; }
        public string SurfaceElevated { get; set; }
        public string TextPrimary { get; set; }
        public string TextSecondary { get; set; }
        public string Accent { get; set; }
        public string AccentMuted { get; set; }
        public string Text { get; set; }
        public string TextMuted { get; set; }
        public string TextInverse { get; set; }
        public string Border { get; set; }
        public string Error { get; set; }
        public string ErrorBg { get; set; }
        public string Warning { get; set; }
        public string WarningBg { get; set; }
        public string Success { get; set; }
        public string SuccessBg { get; set; }
        public string Info { get; set; }
        public string InfoBg { get; set; }
        public string Muted { get; set; }
    }

    public static class ThemeManager
    {
        public static readonly List<VaultTheme> Themes = new List<VaultTheme>
        {
            new VaultTheme
            {
                Name = "Golden Slate",
                Id = "golden-slate",
                Mode = "dark",
                Primary = "#2E3538",
                Background = "#2E3538",
                Surface = "#363D41",
                SurfaceAlt = "#3F474C",
                SurfaceElevated = "#485157",
                TextPrimary = "#EDE8DE",
                TextSecondary = "#B8B1A5",
                Accent = "#D4AF37",
                AccentMuted = "#A8892A",
                Text = "#EDE8DE",
                TextMuted = "#8FA0A8",
                TextInverse = "#1C2226",
                Border = "rgba(212,175,55,0.18)",
                Error = "#E05C4A",
                ErrorBg = "rgba(224,92,74,0.14)",
                Warning = "#E09D34",
                WarningBg = "rgba(224,157,52,0.14)",
                Success = "#5BAD72",
                SuccessBg = "rgba(91,173,114,0.14)",
                Info = "#5B9FBF",
                InfoBg = "rgba(91,159,191,0.14)",
                Muted = "#586672"
            },
            new VaultTheme
            {
                Name = "Solarized Light Revisited",
                Id = "solarized-light-revisited",
                Mode = "light",
                Primary = "#FDF6E3",
                Background = "#FDF6E3",
                Surface = "#F5EFD6",
                SurfaceAlt = "#EDE5C8",
                SurfaceElevated = "#E6DDBA",
                TextPrimary = "#073642",
                TextSecondary = "#586E75",
                Accent = "#268BD2",
                AccentMuted = "#1A6BA8",
                Text = "#073642",
                TextMuted = "#657B83",
                TextInverse = "#FDF6E3",
                Border = "rgba(38,139,210,0.2)",
                Error = "#DC322F",
                ErrorBg = "rgba(220,50,47,0.1)",
                Warning = "#CB4B16",
                WarningBg = "rgba(203,75,22,0.1)",
                Success = "#859900",
                SuccessBg = "rgba(133,153,0,0.1)",
                Info = "#2AA198",
                InfoBg = "rgba(42,161,152,0.1)",
                Muted = "#93A1A1"
            },
            new VaultTheme
            {
                Name = "Cyberpunk Cinder",
                Id = "cyberpunk-cinder",
                Mode = "dark",
                Primary = "#0A1520",
                Background = "#0A1520",
                Surface = "#0F1E2E",
                SurfaceAlt = "#162537",
                SurfaceElevated = "#1D2E42",
                TextPrimary = "#D4CFCF",
                TextSecondary = "#A0AAB2",
                Accent = "#CB4B16",
                AccentMuted = "#9A3A12",
                Text = "#D4CFCF",
                TextMuted = "#587080",
                TextInverse = "#F0EBE0",
                Border = "rgba(203,75,22,0.22)",
                Error = "#FF2A6D",
                ErrorBg = "rgba(255,42,109,0.12)",
                Warning = "#FF9F1C",
                WarningBg = "rgba(255,159,28,0.12)",
                Success = "#05E988",
                SuccessBg = "rgba(5,233,136,0.12)",
                Info = "#00B4D8",
                InfoBg = "rgba(0,180,216,0.12)",
                Muted = "#3D5060"
            },
            new VaultTheme
            {
                Name = "Vintage Velvet",
                Id = "vintage-velvet",
                Mode = "light",
                Primary = "#F5F0E8",
                Background = "#F5F0E8",
                Surface = "#EDE7D9",
                SurfaceAlt = "#E2DAC9",
                SurfaceElevated = "#D8CDB8",
                TextPrimary = "#2C1810",
                TextSecondary = "#5A4A42",
                Accent = "#800020",
                AccentMuted = "#5E0018",
                Text = "#2C1810",
                TextMuted = "#7D6E62",
                TextInverse = "#F5F0E8",
                Border = "rgba(128,0,32,0.2)",
                Error = "#B22222",
                ErrorBg = "rgba(178,34,34,0.1)",
                Warning = "#C47D0E",
                WarningBg = "rgba(196,125,14,0.1)",
                Success = "#2E6B4F",
                SuccessBg = "rgba(46,107,79,0.1)",
                Info = "#2C5F8A",
                InfoBg = "rgba(44,95,138,0.1)",
                Muted = "#9E8E82"
            },
            new VaultTheme
            {
                Name = "Modern Monolith",
                Id = "modern-monolith",
                Mode = "light",
                Primary = "#F8F7F4",
                Background = "#F8F7F4",
                Surface = "#EFEDE8",
                SurfaceAlt = "#E5E2DC",
                SurfaceElevated = "#DBD8D0",
                TextPrimary = "#111111",
                TextSecondary = "#444444",
                Accent = "#1A1A1A",
                AccentMuted = "#444444",
                Text = "#111111",
                TextMuted = "#888888",
                TextInverse = "#F8F7F4",
                Border = "rgba(26,26,26,0.14)",
                Error = "#C0392B",
                ErrorBg = "rgba(192,57,43,0.09)",
                Warning = "#D4892A",
                WarningBg = "rgba(212,137,42,0.09)",
                Success = "#27AE60",
                SuccessBg = "rgba(39,174,96,0.09)",
                Info = "#2980B9",
                InfoBg = "rgba(41,128,185,0.09)",
                Muted = "#AAAAAA"
            },
            new VaultTheme
            {
                Name = "Neon Void",
                Id = "neon-void",
                Mode = "dark",
                Primary = "#0D0D0D",
                Background = "#0D0D0D",
                Surface = "#141414",
                SurfaceAlt = "#1C1C1C",
                SurfaceElevated = "#252525",
                TextPrimary = "#E8E8E8",
                TextSecondary = "#B0B0B0",
                Accent = "#00E5FF",
                AccentMuted = "#008FA8",
                Text = "#E8E8E8",
                TextMuted = "#606060",
                TextInverse = "#0D0D0D",
                Border = "rgba(0,229,255,0.2)",
                Error = "#FF00AA",
                ErrorBg = "rgba(255,0,170,0.12)",
                Warning = "#FFDD00",
                WarningBg = "rgba(255,221,0,0.12)",
                Success = "#39FF14",
                SuccessBg = "rgba(57,255,20,0.12)",
                Info = "#BD00FF",
                InfoBg = "rgba(189,0,255,0.12)",
                Muted = "#383838"
            },
            new VaultTheme
            {
                Name = "Ocean Mist",
                Id = "ocean-mist",
                Mode = "light",
                Primary = "#EEF2F5",
                Background = "#EEF2F5",
                Surface = "#E3EAEF",
                SurfaceAlt = "#D6E0E8",
                SurfaceElevated = "#C9D6DF",
                TextPrimary = "#1A2A35",
                TextSecondary = "#4A5A65",
                Accent = "#006994",
                AccentMuted = "#004F6E",
                Text = "#1A2A35",
                TextMuted = "#708090",
                TextInverse = "#FFFFFF",
                Border = "rgba(0,105,148,0.18)",
                Error = "#CD5C5C",
                ErrorBg = "rgba(205,92,92,0.1)",
                Warning = "#C4822A",
                WarningBg = "rgba(196,130,42,0.1)",
                Success = "#20B2AA",
                SuccessBg = "rgba(32,178,170,0.1)",
                Info = "#4682B4",
                InfoBg = "rgba(70,130,180,0.1)",
                Muted = "#8FA0AA"
            },
            new VaultTheme
            {
                Name = "Royal Tangerine",
                Id = "royal-tangerine",
                Mode = "dark",
                Primary = "#1A0A2E",
                Background = "#1A0A2E",
                Surface = "#231240",
                SurfaceAlt = "#2C1850",
                SurfaceElevated = "#361F62",
                TextPrimary = "#EEE8F8",
                TextSecondary = "#B8B0D0",
                Accent = "#F28500",
                AccentMuted = "#B86500",
                Text = "#EEE8F8",
                TextMuted = "#7A6A9A",
                TextInverse = "#1A0A2E",
                Border = "rgba(242,133,0,0.2)",
                Error = "#FF4500",
                ErrorBg = "rgba(255,69,0,0.13)",
                Warning = "#FFB700",
                WarningBg = "rgba(255,183,0,0.13)",
                Success = "#00E676",
                SuccessBg = "rgba(0,230,118,0.13)",
                Info = "#7B61FF",
                InfoBg = "rgba(123,97,255,0.13)",
                Muted = "#4A3A6A"
            },
            new VaultTheme
            {
                Name = "Crimson Bloom",
                Id = "crimson-bloom",
                Mode = "dark",
                Primary = "#2A0A0A",
                Background = "#2A0A0A",
                Surface = "#361212",
                SurfaceAlt = "#421818",
                SurfaceElevated = "#4E1F1F",
                TextPrimary = "#F5E8EA",
                TextSecondary = "#C5B8BA",
                Accent = "#E8A0B4",
                AccentMuted = "#B07086",
                Text = "#F5E8EA",
                TextMuted = "#9A7A82",
                TextInverse = "#2A0A0A",
                Border = "rgba(232,160,180,0.2)",
                Error = "#FF4444",
                ErrorBg = "rgba(255,68,68,0.14)",
                Warning = "#E8A030",
                WarningBg = "rgba(232,160,48,0.14)",
                Success = "#48D090",
                SuccessBg = "rgba(72,208,144,0.14)",
                Info = "#90A8E8",
                InfoBg = "rgba(144,168,232,0.14)",
                Muted = "#5A3A3E"
            },
            new VaultTheme
            {
                Name = "Amethyst Frost",
                Id = "amethyst-frost",
                Mode = "light",
                Primary = "#FAFAFE",
                Background = "#FAFAFE",
                Surface = "#F0EEF8",
                SurfaceAlt = "#E4E0F4",
                SurfaceElevated = "#D8D2F0",
                TextPrimary = "#1A0A2E",
                TextSecondary = "#4A3A6A",
                Accent = "#6B30A8",
                AccentMuted = "#4E2280",
                Text = "#1A0A2E",
                TextMuted = "#7A6A9A",
                TextInverse = "#FAFAFE",
                Border = "rgba(107,48,168,0.18)",
                Error = "#C2185B",
                ErrorBg = "rgba(194,24,91,0.09)",
                Warning = "#E67E22",
                WarningBg = "rgba(230,126,34,0.09)",
                Success = "#388E3C",
                SuccessBg = "rgba(56,142,60,0.09)",
                Info = "#0288D1",
                InfoBg = "rgba(2,136,209,0.09)",
                Muted = "#C0B8D8"
            },
            new VaultTheme
            {
                Name = "Catppuccin Mocha",
                Id = "catppuccin-mocha",
                Mode = "dark",
                Primary = "#1E1E2E",
                Background = "#1E1E2E",
                Surface = "#181825",
                SurfaceAlt = "#11111B",
                SurfaceElevated = "#313244",
                TextPrimary = "#CDD6F4",
                TextSecondary = "#A6ADC8",
                Accent = "#CBA6F7",
                AccentMuted = "#957FB8",
                Text = "#CDD6F4",
                TextMuted = "#6C7086",
                TextInverse = "#11111B",
                Border = "rgba(203,166,247,0.2)",
                Error = "#F38BA8",
                ErrorBg = "rgba(243,139,168,0.1)",
                Warning = "#FAB387",
                WarningBg = "rgba(250,179,135,0.1)",
                Success = "#A6E3A1",
                SuccessBg = "rgba(166,227,161,0.1)",
                Info = "#89B4FA",
                InfoBg = "rgba(137,180,250,0.1)",
                Muted = "#45475A"
            },
            new VaultTheme
            {
                Name = "Dracula",
                Id = "dracula",
                Mode = "dark",
                Primary = "#282A36",
                Background = "#282A36",
                Surface = "#343746",
                SurfaceAlt = "#44475A",
                SurfaceElevated = "#6272A4",
                TextPrimary = "#F8F8F2",
                TextSecondary = "#BD93F9",
                Accent = "#FF79C6",
                AccentMuted = "#D163A3",
                Text = "#F8F8F2",
                TextMuted = "#6272A4",
                TextInverse = "#282A36",
                Border = "rgba(189,147,249,0.2)",
                Error = "#FF5555",
                ErrorBg = "rgba(255,85,85,0.1)",
                Warning = "#F1FA8C",
                WarningBg = "rgba(241,250,140,0.1)",
                Success = "#50FA7B",
                SuccessBg = "rgba(80,250,123,0.1)",
                Info = "#8BE9FD",
                InfoBg = "rgba(139,233,253,0.1)",
                Muted = "#44475A"
            },
            new VaultTheme
            {
                Name = "Tokyo Night Storm",
                Id = "tokyo-night-storm",
                Mode = "dark",
                Primary = "#24283B",
                Background = "#24283B",
                Surface = "#1F2335",
                SurfaceAlt = "#1A1B26",
                SurfaceElevated = "#292E42",
                TextPrimary = "#A9B1D6",
                TextSecondary = "#9ECE6A",
                Accent = "#7AA2F7",
                AccentMuted = "#5B7CC4",
                Text = "#A9B1D6",
                TextMuted = "#565F89",
                TextInverse = "#1A1B26",
                Border = "rgba(122,162,247,0.2)",
                Error = "#F7768E",
                ErrorBg = "rgba(247,118,142,0.1)",
                Warning = "#E0AF68",
                WarningBg = "rgba(224,175,104,0.1)",
                Success = "#73DACA",
                SuccessBg = "rgba(115,218,202,0.1)",
                Info = "#B4F9F8",
                InfoBg = "rgba(180,249,248,0.1)",
                Muted = "#32344A"
            },
            new VaultTheme
            {
                Name = "GitHub Light Default",
                Id = "github-light",
                Mode = "light",
                Primary = "#FFFFFF",
                Background = "#FFFFFF",
                Surface = "#F6F8FA",
                SurfaceAlt = "#EAEFEF",
                SurfaceElevated = "#D0D7DE",
                TextPrimary = "#1F2328",
                TextSecondary = "#65717E",
                Accent = "#0969DA",
                AccentMuted = "#0550AE",
                Text = "#1F2328",
                TextMuted = "#6E7781",
                TextInverse = "#FFFFFF",
                Border = "rgba(31,35,40,0.15)",
                Error = "#D1242F",
                ErrorBg = "rgba(209,36,47,0.1)",
                Warning = "#9A6700",
                WarningBg = "rgba(154,103,0,0.1)",
                Success = "#1A7F37",
                SuccessBg = "rgba(26,127,55,0.1)",
                Info = "#0969DA",
                InfoBg = "rgba(9,105,218,0.1)",
                Muted = "#AFB8C1"
            },
            new VaultTheme
            {
                Name = "Monokai Pro",
                Id = "monokai-pro",
                Mode = "dark",
                Primary = "#2D2A2E",
                Background = "#2D2A2E",
                Surface = "#37343A",
                SurfaceAlt = "#221F22",
                SurfaceElevated = "#403E41",
                TextPrimary = "#FCFCFA",
                TextSecondary = "#A9DC76",
                Accent = "#FFD866",
                AccentMuted = "#C9AB51",
                Text = "#FCFCFA",
                TextMuted = "#727072",
                TextInverse = "#2D2A2E",
                Border = "rgba(255,216,102,0.2)",
                Error = "#FF6188",
                ErrorBg = "rgba(255,97,136,0.1)",
                Warning = "#FC9867",
                WarningBg = "rgba(252,152,103,0.1)",
                Success = "#A9DC76",
                SuccessBg = "rgba(169,220,118,0.1)",
                Info = "#78DCE8",
                InfoBg = "rgba(120,220,232,0.1)",
                Muted = "#5B595C"
            }
        };

        public static VaultTheme GetTheme(string name = null, int index = 0)
        {
            if (name != null)
            {
                var found = Themes.FirstOrDefault(t => t.Name == name);
                if (found != null) return found;
            }
            if (index >= 0 && index < Themes.Count)
            {
                return Themes[index];
            }
            return Themes[0];
        }
    }
}
