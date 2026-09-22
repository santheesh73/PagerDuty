import React from 'react';
import { SeverityCount } from '../../types/analytics';
import { Card } from '../shared/Card';
import { EmptyState } from '../shared/EmptyState';

export interface SeverityDistributionProps {
  data?: SeverityCount[];
  isLoading?: boolean;
}

const severityConfig: Record<string, { label: string; color: string; bg: string }> = {
  CRITICAL: { label: 'Critical', color: 'bg-rose-500', bg: 'text-rose-400' },
  HIGH: { label: 'High', color: 'bg-amber-500', bg: 'text-amber-400' },
  MEDIUM: { label: 'Medium', color: 'bg-sky-500', bg: 'text-sky-400' },
  LOW: { label: 'Low', color: 'bg-slate-400', bg: 'text-slate-400' },
};

export const SeverityDistribution: React.FC<SeverityDistributionProps> = ({
  data = [],
  isLoading = false,
}) => {
  const total = data.reduce((acc, curr) => acc + curr.count, 0);

  return (
    <Card
      title="Severity Distribution"
      subtitle="Canonical incident severity allocation over time"
    >
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : data.length === 0 || total === 0 ? (
        <EmptyState
          title="No severity data"
          description="Zero incidents recorded in this window."
        />
      ) : (
        <div className="space-y-4 pt-2">
          {/* Stacked Bar */}
          <div className="w-full h-3 rounded-full bg-slate-800 overflow-hidden flex">
            {data.map((item) => {
              const pct = total > 0 ? (item.count / total) * 100 : 0;
              const config = severityConfig[item.severity.toUpperCase()] || {
                label: item.severity,
                color: 'bg-indigo-500',
                bg: 'text-indigo-400',
              };
              if (pct === 0) return null;
              return (
                <div
                  key={item.severity}
                  className={`h-full ${config.color} transition-all duration-500`}
                  style={{ width: `${pct}%` }}
                  title={`${config.label}: ${item.count} (${Math.round(pct)}%)`}
                />
              );
            })}
          </div>

          {/* Legend and stats */}
          <div className="grid grid-cols-2 gap-3 pt-2">
            {['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map((sev) => {
              const item = data.find((d) => d.severity.toUpperCase() === sev) || {
                severity: sev,
                count: 0,
              };
              const config = severityConfig[sev];
              const pct = total > 0 ? Math.round((item.count / total) * 100) : 0;

              return (
                <div
                  key={sev}
                  data-testid={`severity-stat-${sev.toLowerCase()}`}
                  className="p-3 rounded-lg bg-slate-950/40 border border-slate-800 flex items-center justify-between"
                >
                  <div className="flex items-center gap-2">
                    <span className={`w-2.5 h-2.5 rounded-full ${config.color}`} />
                    <span className="text-xs font-semibold text-slate-200">{config.label}</span>
                  </div>
                  <div className="text-right font-mono">
                    <span className="text-sm font-bold text-white">{item.count}</span>
                    <span className="text-xs text-slate-500 ml-1.5">({pct}%)</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
};
