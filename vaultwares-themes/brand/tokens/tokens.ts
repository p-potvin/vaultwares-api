export const vaultTokens = {
  color: {
    base: '#002B36',
    paper: '#FDF6E3',
    paperBright: '#FDFCF7',
    ink: '#002B36',
    slate: '#4A5459',
    muted: '#586E75',
    gold: '#CC9B21',
    goldMuted: '#B78C1E',
    goldLight: '#E5C06A',
    cyan: '#21B8CC',
    green: '#4ECC21',
    burgundy: '#A63D40',
    deepSea: '#0A2540',
    borderLight: 'rgba(0, 43, 54, 0.14)',
    borderDark: 'rgba(253, 246, 227, 0.18)',
  },
  semantic: {
    light: {
      background: '#FDF6E3',
      surface: '#FDFCF7',
      surfaceElevated: 'rgba(253, 252, 247, 0.86)',
      textPrimary: '#002B36',
      textSecondary: '#586E75',
      accent: '#CC9B21',
      accentHover: '#B78C1E',
      borderSubtle: 'rgba(0, 43, 54, 0.14)',
      focusRing: '#21B8CC',
      success: '#4ECC21',
      warning: '#CC9B21',
      danger: '#A63D40',
    },
    dark: {
      background: '#002B36',
      surface: '#4A5459',
      surfaceElevated: 'rgba(74, 84, 89, 0.72)',
      textPrimary: '#FDF6E3',
      textSecondary: '#D8D0B8',
      accent: '#CC9B21',
      accentHover: '#E5C06A',
      borderSubtle: 'rgba(253, 246, 227, 0.18)',
      focusRing: '#21B8CC',
      success: '#4ECC21',
      warning: '#CC9B21',
      danger: '#A63D40',
    },
  },
  typography: {
    fontFamily: {
      sans: ['"Segoe UI Semilight"', '"Segoe UI"', 'Inter', 'system-ui', 'sans-serif'],
      mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
    },
    scale: {
      display: { fontSize: '56px', lineHeight: '64px', fontWeight: 300 },
      heading: { fontSize: '32px', lineHeight: '40px', fontWeight: 400 },
      body: { fontSize: '16px', lineHeight: '26px', fontWeight: 400 },
      label: { fontSize: '13px', lineHeight: '20px', fontWeight: 500 },
    },
  },
  spacing: {
    0: '0',
    1: '4px',
    2: '8px',
    3: '12px',
    4: '16px',
    6: '24px',
    8: '32px',
    10: '40px',
    12: '48px',
    16: '64px',
  },
  radius: {
    sm: '4px',
    md: '8px',
    lg: '12px',
    xl: '16px',
    panel: '20px',
  },
  motion: {
    fast: '120ms',
    base: '180ms',
    slow: '240ms',
    entryEase: 'ease-out',
    stateEase: 'ease-in-out',
  },
  glass: {
    overlayOpacityMax: 0.6,
    blurSoft: '8px',
    blurPanel: '16px',
    blurStrong: '20px',
    borderLight: 'rgba(255, 255, 255, 0.36)',
    borderDark: 'rgba(253, 246, 227, 0.18)',
  },
} as const

export const colors = vaultTokens.color
export const typography = vaultTokens.typography
export const spacing = vaultTokens.spacing
export const radius = vaultTokens.radius
export const motion = vaultTokens.motion
export const glass = vaultTokens.glass

export type VaultTokens = typeof vaultTokens
export type VaultMode = keyof typeof vaultTokens.semantic
