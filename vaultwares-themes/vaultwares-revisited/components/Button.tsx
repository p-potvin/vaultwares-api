import React from 'react';

interface ButtonProps {
  variant?: 'primary' | 'secondary' | 'ghost';
  mode?: 'console' | 'warm';
  children?: React.ReactNode;
  className?: string;
  onClick?: () => void;
  type?: 'button' | 'submit' | 'reset';
}

export function Button({ variant = 'primary', mode = 'console', className = '', children, ...props }: ButtonProps) {
  let baseClass = 'px-4 py-2 font-medium rounded-lg transition-colors whitespace-nowrap focus:outline-none focus:ring-2 focus:ring-offset-2';
  
  if (mode === 'console') {
    if (variant === 'primary') {
      baseClass += ' bg-[var(--vault-console-gold)] text-[#161320] hover:bg-[#EACD76] focus:ring-[var(--vault-console-gold)] focus:ring-offset-[var(--vault-console-bg)]';
    } else if (variant === 'secondary') {
      baseClass += ' bg-[var(--vault-console-elevated)] text-[var(--vault-console-gold)] border border-[var(--vault-console-gold)] hover:bg-[var(--vault-console-raised)] focus:ring-[var(--vault-console-gold)] focus:ring-offset-[var(--vault-console-bg)]';
    } else {
      baseClass += ' text-[var(--vault-console-text-secondary)] hover:text-[#fff] hover:bg-[rgba(255,255,255,0.05)] focus:ring-[var(--vault-console-text-secondary)] focus:ring-offset-[var(--vault-console-bg)]';
    }
  } else {
    // Warm mode
    if (variant === 'primary') {
      baseClass += ' bg-[#161320] text-[#F5F1E8] hover:bg-[#2A2340] focus:ring-[#161320] focus:ring-offset-[#F5F1E8]';
    } else if (variant === 'secondary') {
      baseClass += ' bg-[var(--vault-warm-raised)] text-[#161320] border border-[#161320] hover:bg-[var(--vault-warm-muted)] focus:ring-[#161320] focus:ring-offset-[#F5F1E8]';
    } else {
      baseClass += ' text-[#4A5459] hover:text-[#161320] hover:bg-[rgba(0,0,0,0.05)] focus:ring-[#4A5459] focus:ring-offset-[#F5F1E8]';
    }
  }

  return (
    <button className={`${baseClass} ${className}`} {...props}>
      {children}
    </button>
  );
}
