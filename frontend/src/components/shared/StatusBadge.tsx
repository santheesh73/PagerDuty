import React from 'react';
import { IncidentStatus } from '../../types/incident';
import { cn } from '../../lib/cn';

export interface StatusBadgeProps {
  status: IncidentStatus | string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className }) => {
  const normalized = status.toLowerCase();

  const configs: Record<string, { label: string; dotClass: string; badgeClass: string }> = {
    triggered: {
      label: 'Triggered',
      dotClass: 'bg-rose-400 animate-pulse',
      badgeClass: 'bg-rose-950/70 text-rose-300 border-rose-800/80',
    },
    acknowledged: {
      label: 'Acknowledged',
      dotClass: 'bg-amber-400',
      badgeClass: 'bg-amber-950/70 text-amber-300 border-amber-800/80',
    },
    resolved: {
      label: 'Resolved',
      dotClass: 'bg-emerald-400',
      badgeClass: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/80',
    },
  };

  const config = configs[normalized] || {
    label: status,
    dotClass: 'bg-slate-400',
    badgeClass: 'bg-slate-900 text-slate-300 border-slate-700',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border tracking-wide uppercase',
        config.badgeClass,
        className
      )}
    >
      <span className={cn('w-1.5 h-1.5 rounded-full', config.dotClass)} aria-hidden="true" />
      {config.label}
    </span>
  );
};
