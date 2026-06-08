import type { Config } from 'tailwindcss'
import { vaultTokens } from './tokens'

const config = {
  darkMode: 'class',
  content: [
    './src/**/*.{ts,tsx,js,jsx,html}',
    './examples/**/*.{ts,tsx,js,jsx,html}',
  ],
  theme: {
    extend: {
      colors: {
        vault: {
          base: vaultTokens.color.base,
          paper: vaultTokens.color.paper,
          paperBright: vaultTokens.color.paperBright,
          ink: vaultTokens.color.ink,
          slate: vaultTokens.color.slate,
          muted: vaultTokens.color.muted,
          gold: vaultTokens.color.gold,
          goldMuted: vaultTokens.color.goldMuted,
          goldLight: vaultTokens.color.goldLight,
          cyan: vaultTokens.color.cyan,
          green: vaultTokens.color.green,
          burgundy: vaultTokens.color.burgundy,
          deepSea: vaultTokens.color.deepSea,
        },
      },
      fontFamily: {
        sans: vaultTokens.typography.fontFamily.sans,
        mono: vaultTokens.typography.fontFamily.mono,
      },
      borderRadius: {
        vault: vaultTokens.radius.md,
        'vault-panel': vaultTokens.radius.panel,
      },
      transitionDuration: {
        vault: vaultTokens.motion.base,
      },
    },
  },
} satisfies Config

export default config
