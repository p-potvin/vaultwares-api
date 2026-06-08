import { vaultTokens } from '../../brand/tokens/tokens'

export const VaultCoreBadge = ({ mode }: { mode: 'server' | 'local' }) => {
  const isLocal = mode === 'local'
  const accent = isLocal ? vaultTokens.color.green : vaultTokens.color.gold

  const label = isLocal ? 'Local' : 'VaultWares Hosted'
  const description = isLocal
    ? 'Running locally on this device. Data is not sent to external servers.'
    : 'Running on VaultWares secure cloud infrastructure.'

  return (
    <div
      role="status"
      aria-label={`Environment: ${label}`}
      title={description}
      style={{
        backgroundColor: `${accent}15`,
        color: accent,
        border: `1px solid ${accent}40`,
        borderRadius: vaultTokens.radius.md,
        padding: `${vaultTokens.spacing[1]} ${vaultTokens.spacing[3]}`,
        fontSize: vaultTokens.typography.scale.label.fontSize,
        cursor: 'help',
      }}
    >
      {label}
    </div>
  )
}
