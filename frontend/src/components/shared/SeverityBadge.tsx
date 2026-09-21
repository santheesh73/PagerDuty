import React from 'react';
import { IncidentSeverity } from '../../types/incident';
import { cn } from '../../lib/cn';

export interface SeverityBadgeProps {
  severity: IncidentSeverity | string;
  className?: string;
}

export const SeverityBadge: React.FC<SeverityBadgeProps> = ({ severity, className }) => {
  const normalized = severity.toLowerCase();

  const configs: Record<string, { label: string; badgeClass: string }> = {
    critical: {
      label: 'Critical',
      badgeClass: 'bg-red-950/80 text-red-300 border-red-800',
    },
    high: {
      label: 'High',
      badgeClass: 'bg-orange-950/80 text-orange-300 border-orange-800',
    },
    medium: {
      label: 'Medium',
      badgeClass: 'bg-amber-950/80 text-amber-300 border-amber-800',
    },
    low: {
      label: 'Low',
      badgeClass: 'bg-blue-950/80 text-blue-300 border-blue-800',
    },
  };

  const config = configs[normalized] || {
    label: severity,
    badgeClass: 'bg-slate-900 text-slate-300 border-slate-700',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider border',
        config.badgeClass,
        className
      )}
    >
      {config.label}
    </span>
  );
};
