import React from 'react';
import { Activity, AlertOctagon, CheckCircle2, Clock, Zap } from 'lucide-react';
import { AnalyticsSummary } from '../../types/analytics';
import { Card } from '../shared/Card';
import { formatDurationSeconds } from '../../lib/duration';

export interface AnalyticsKpisProps {
  summary?: AnalyticsSummary;
  isLoading?: boolean;
}

export const AnalyticsKpis: React.FC<AnalyticsKpisProps> = ({ summary, isLoading = false }) => {

  const kpis = [
    {
      title: 'Total Incidents',
      value: summary?.incident_count ?? (isLoading ? '—' : 0),
      subtitle: `Past ${summary?.range_days ?? 30} days`,
      icon: Activity,
      iconColor: 'text-indigo-400',
      bgColor: 'bg-indigo-500/10 border-indigo-500/20',
      testId: 'kpi-incident-count',
    },
    {
      title: 'Active Incidents',
      value: summary?.active_incidents ?? (isLoading ? '—' : 0),
      subtitle: 'Triggered or Acknowledged',
      icon: Zap,
      iconColor: 'text-amber-400',
      bgColor: 'bg-amber-500/10 border-amber-500/20',
      testId: 'kpi-active-incidents',
    },
    {
      title: 'Critical Incidents',
      value: summary?.critical_incidents ?? (isLoading ? '—' : 0),
      subtitle: 'Severity CRITICAL',
      icon: AlertOctagon,
      iconColor: 'text-rose-400',
      bgColor: 'bg-rose-500/10 border-rose-500/20',
      testId: 'kpi-critical-incidents',
    },
    {
      title: 'MTTA (Acknowledge)',
      value: isLoading ? '—' : formatDurationSeconds(summary?.mtta_seconds),
      subtitle: 'Mean Time to Acknowledge',
      icon: Clock,
      iconColor: 'text-sky-400',
      bgColor: 'bg-sky-500/10 border-sky-500/20',
      testId: 'kpi-mtta',
    },
    {
      title: 'MTTR (Resolve)',
      value: isLoading ? '—' : formatDurationSeconds(summary?.mttr_seconds),
      subtitle: 'Mean Time to Resolve',
      icon: CheckCircle2,
      iconColor: 'text-emerald-400',
      bgColor: 'bg-emerald-500/10 border-emerald-500/20',
      testId: 'kpi-mttr',
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
      {kpis.map((kpi) => {
        const Icon = kpi.icon;
        return (
          <Card key={kpi.title} className="p-4" data-testid={kpi.testId}>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                {kpi.title}
              </span>
              <div
                className={`w-7 h-7 rounded-lg border flex items-center justify-center ${kpi.bgColor} ${kpi.iconColor}`}
              >
                <Icon className="w-4 h-4" />
              </div>
            </div>
            <div className="mt-3">
              <div className="text-2xl font-bold text-white tracking-tight">
                {kpi.value}
              </div>
              <p className="text-xs text-slate-500 mt-1">{kpi.subtitle}</p>
            </div>
          </Card>
        );
      })}
    </div>
  );
};
