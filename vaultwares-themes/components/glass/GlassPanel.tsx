import type { CSSProperties, ReactNode } from 'react'

export type GlassVariant =
  | 'liquid'
  | 'vibrant'
  | 'solarized-frosted'
  | 'frosted'
  | 'clear'
  | 'subtle'

export interface GlassPanelProps {
  variant?: GlassVariant
  className?: string
  children?: ReactNode
  tint?: string
  tintOpacity?: number
  blur?: number
  style?: CSSProperties
}

const variantClasses: Record<GlassVariant, string> = {
  liquid: 'bg-white/10 backdrop-blur-md border border-white/30 shadow-[0_8px_32px_rgba(0,43,54,0.18)]',
  vibrant: 'bg-gradient-to-br from-vault-cyan/20 to-vault-gold/20 backdrop-blur-md border border-white/40 shadow-lg',
  'solarized-frosted': 'bg-vault-paper/45 backdrop-blur-md border border-vault-muted/20 shadow-sm',
  frosted: 'bg-white/40 backdrop-blur-md border border-white/50 shadow-md',
  clear: 'bg-white/10 backdrop-blur-sm border border-white/20 shadow-sm',
  subtle: 'bg-white/5 backdrop-blur-[2px] border border-white/10 shadow-none',
}

function hexToRgba(hex: string, alpha: number) {
  const value = hex.replace('#', '')

  if (value.length === 3) {
    const red = parseInt(value[0] + value[0], 16)
    const green = parseInt(value[1] + value[1], 16)
    const blue = parseInt(value[2] + value[2], 16)
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`
  }

  if (value.length === 6 || value.length === 8) {
    const red = parseInt(value.slice(0, 2), 16)
    const green = parseInt(value.slice(2, 4), 16)
    const blue = parseInt(value.slice(4, 6), 16)
    return `rgba(${red}, ${green}, ${blue}, ${alpha})`
  }

  return hex
}

export function GlassPanel({
  variant = 'frosted',
  className = '',
  children,
  tint,
  tintOpacity = 0.08,
  blur,
  style,
}: GlassPanelProps) {
  const computedStyle: CSSProperties = {}

  if (tint) {
    const isHex = /^#([A-Fa-f0-9]{3,8})$/.test(tint)
    computedStyle.backgroundColor = isHex ? hexToRgba(tint, tintOpacity) : tint
  }

  if (typeof blur === 'number') {
    computedStyle.backdropFilter = `blur(${blur}px)`
    computedStyle.WebkitBackdropFilter = `blur(${blur}px)`
  }

  return (
    <div className={`rounded-xl p-4 ${variantClasses[variant]} ${className}`} style={{ ...style, ...computedStyle }}>
      {children}
    </div>
  )
}
