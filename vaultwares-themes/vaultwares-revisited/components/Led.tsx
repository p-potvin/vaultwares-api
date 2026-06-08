interface LedProps {
  status?: 'online' | 'relay' | 'sync' | 'warning' | 'alert';
  pulse?: boolean;
  className?: string;
  size?: number;
}

export function Led({ status = 'online', pulse = true, className = '', size = 8 }: LedProps) {
  const statusColors = {
    online: 'var(--vault-signal-online)',
    relay: 'var(--vault-signal-relay)',
    sync: 'var(--vault-signal-sync)',
    warning: 'var(--vault-signal-warning)',
    alert: 'var(--vault-signal-alert)',
  };

  const backgroundColor = statusColors[status];

  return (
    <div
      className={`rounded-full flex-shrink-0 ${pulse ? 'vw-led' : ''} ${className}`}
      style={{
        width: size,
        height: size,
        backgroundColor,
        boxShadow: `0 0 ${size}px ${backgroundColor}`,
      }}
      aria-label={`Status: ${status}`}
    />
  );
}
