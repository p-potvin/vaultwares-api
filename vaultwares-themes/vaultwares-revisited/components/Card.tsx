import React from 'react';

interface CardProps {
  mode: 'console' | 'warm';
  children: React.ReactNode;
  className?: string;
}

export function Card({ mode, children, className = '' }: CardProps) {
  const cardClass = mode === 'console' ? 'vw-card text-vw-console-text-secondary' : 'vw-warm-card text-[#161320]';
  return (
    <div className={`p-6 md:p-8 backdrop-blur-sm ${cardClass} ${className}`}>
      {children}
    </div>
  );
}
