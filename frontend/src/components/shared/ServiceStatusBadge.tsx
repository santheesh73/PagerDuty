import React from 'react';
import { ServiceStatus } from '../../types/service';
import { cn } from '../../lib/cn';

export interface ServiceStatusBadgeProps {
  status: ServiceStatus | string;
  className?: string;
}

export const ServiceStatusBadge: React.FC<ServiceStatusBadgeProps> = ({ status, className }) => {
  const normalized = (status || '').toUpperCase();

  const configs: Record<string, { label: string; dotClass: string; badgeClass: string }> = {
    HEALTHY: {
      label: 'Healthy',
      dotClass: 'bg-emerald-400',
      badgeClass: 'bg-emerald-950/70 text-emerald-300 border-emerald-800/80',
    },
    DEGRADED: {
      label: 'Degraded',
      dotClass: 'bg-amber-400',
      badgeClass: 'bg-amber-950/70 text-amber-300 border-amber-800/80',
    },
    DOWN: {
      label: 'Down',
      dotClass: 'bg-rose-500 animate-pulse',
      badgeClass: 'bg-rose-950/70 text-rose-300 border-rose-800/80',
    },
    MAINTENANCE: {
      label: 'Maintenance',
      dotClass: 'bg-blue-400',
      badgeClass: 'bg-blue-950/70 text-blue-300 border-blue-800/80',
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
