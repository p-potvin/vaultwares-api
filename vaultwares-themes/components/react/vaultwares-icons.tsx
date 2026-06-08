// src/icons/vaultwares-icons.tsx

export type VaultWaresIconName =
  | 'relay-core'
  | 'relay-distributed'
  | 'utility-block'
  | 'utility-channel'
  | 'vw-angular'
  | 'vw-core'

type VaultWaresIconProps = {
  className?: string
}

export function RelayCoreIcon({
  className = 'h-8 w-8',
}: VaultWaresIconProps) {
  return (
    <svg
      viewBox="0 0 128 128"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle cx="64" cy="64" r="14" fill="#D6A441" />

      <circle cx="36" cy="64" r="6" fill="#B07CFF" />
      <circle cx="92" cy="64" r="6" fill="#55D6FF" />
      <circle cx="64" cy="36" r="6" fill="#6BE675" />
      <circle cx="64" cy="92" r="6" fill="#FF8F3D" />

      <path
        d="M42 64H86"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />

      <path
        d="M64 42V86"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function RelayDistributedIcon({
  className = 'h-8 w-8',
}: VaultWaresIconProps) {
  return (
    <svg
      viewBox="0 0 128 128"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <circle cx="64" cy="64" r="10" fill="#D6A441" />

      <circle cx="32" cy="48" r="6" fill="#B07CFF" />
      <circle cx="96" cy="48" r="6" fill="#55D6FF" />
      <circle cx="96" cy="80" r="6" fill="#6BE675" />
      <circle cx="32" cy="80" r="6" fill="#FF8F3D" />

      <path
        d="M40 50L56 60"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />

      <path
        d="M72 60L88 50"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />

      <path
        d="M72 68L88 78"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />

      <path
        d="M40 78L56 68"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
      />
    </svg>
  )
}

export function UtilityBlockIcon({
  className = 'h-8 w-8',
}: VaultWaresIconProps) {
  return (
    <svg
      viewBox="0 0 128 128"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M38 34H90V52H72V76H90V94H38V34Z"
        fill="#D6A441"
      />

      <rect
        x="72"
        y="52"
        width="18"
        height="24"
        fill="currentColor"
      />

      <circle cx="96" cy="32" r="5" fill="#B07CFF" />
    </svg>
  )
}

export function UtilityChannelIcon({
  className = 'h-8 w-8',
}: VaultWaresIconProps) {
  return (
    <svg
      viewBox="0 0 128 128"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <rect
        x="34"
        y="34"
        width="60"
        height="60"
        rx="14"
        fill="#B07CFF"
      />

      <rect
        x="56"
        y="24"
        width="16"
        height="80"
        rx="8"
        fill="currentColor"
      />

      <circle cx="96" cy="32" r="5" fill="#D6A441" />
    </svg>
  )
}

export function VWAngularIcon({
  className = 'h-8 w-8',
}: VaultWaresIconProps) {
  return (
    <svg
      viewBox="0 0 128 128"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M28 38L44 90H56L64 62L72 90H84L100 38"
        stroke="#D6A441"
        strokeWidth="10"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      <circle cx="98" cy="30" r="5" fill="#B07CFF" />
    </svg>
  )
}

export function VWCoreIcon({
  className = 'h-8 w-8',
}: VaultWaresIconProps) {
  return (
    <svg
      viewBox="0 0 128 128"
      className={className}
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M34 42L48 82H58L64 62L70 82H80L94 42"
        stroke="#B07CFF"
        strokeWidth="9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      <rect
        x="42"
        y="92"
        width="44"
        height="8"
        rx="4"
        fill="#D6A441"
      />

      <circle cx="96" cy="32" r="5" fill="#55D6FF" />
    </svg>
  )
}

export const vaultWaresIcons = [
  {
    name: 'Relay Core',
    component: RelayCoreIcon,
  },

  {
    name: 'Relay Distributed',
    component: RelayDistributedIcon,
  },

  {
    name: 'Utility Block',
    component: UtilityBlockIcon,
  },

  {
    name: 'Utility Channel',
    component: UtilityChannelIcon,
  },

  {
    name: 'VW Angular',
    component: VWAngularIcon,
  },

  {
    name: 'VW Core',
    component: VWCoreIcon,
  },

]
