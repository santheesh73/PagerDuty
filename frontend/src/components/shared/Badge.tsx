import React from 'react';
import { cn } from '../../lib/cn';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'warning' | 'error' | 'neutral' | 'info';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'neutral',
  className,
}) => {
  const styles = {
    success: 'bg-emerald-950/80 text-emerald-400 border-emerald-800/80',
    warning: 'bg-amber-950/80 text-amber-400 border-amber-800/80',
    error: 'bg-rose-950/80 text-rose-400 border-rose-800/80',
    neutral: 'bg-slate-800/80 text-slate-300 border-slate-700/80',
    info: 'bg-sky-950/80 text-sky-400 border-sky-800/80',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border tracking-wide',
        styles[variant],
        className
      )}
    >
      {children}
    </span>
  );
};
