import React from 'react';
import { Link } from 'react-router-dom';
import { PageHeader } from '../components/shared/PageHeader';
import { Card } from '../components/shared/Card';
import { ErrorState } from '../components/shared/ErrorState';
import { IncidentTable } from '../components/incident/IncidentTable';
import { useIncidents } from '../hooks/useIncidents';
import {
  AlertOctagon,
  BellRing,
  CheckCircle2,
  Activity,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';

export const Dashboard: React.FC = () => {
  const { data: incidents = [], isLoading, isError, error, refetch } = useIncidents(
    {},
    { refetchInterval: 15_000 }
  );

  if (isError) {
    return (
      <div>
        <PageHeader
          title="Operations Dashboard"
          description="Live operational metrics, active incident queues, and system state."
        />
        <ErrorState
          title="Failed to load dashboard data"
          message={error instanceof Error ? error.message : 'Could not retrieve incident data from server.'}
          onRetry={() => refetch()}
        />
      </div>
    );
  }

  // Derive operational metrics from authoritative incident dataset safely
  const incidentList = Array.isArray(incidents) ? incidents : [];

  const activeIncidents = incidentList.filter(
    (inc) => inc.status?.toLowerCase() !== 'resolved'
  );

  const criticalCount = activeIncidents.filter(
    (inc) => inc.severity?.toLowerCase() === 'critical'
  ).length;

  const triggeredCount = activeIncidents.filter(
    (inc) => inc.status?.toLowerCase() === 'triggered'
  ).length;

  const acknowledgedCount = activeIncidents.filter(
    (inc) => inc.status?.toLowerCase() === 'acknowledged'
  ).length;

  // "Needs Attention": Triggered or Active Critical incidents
  const needsAttention = activeIncidents
    .filter(
      (inc) =>
        inc.status?.toLowerCase() === 'triggered' ||
        inc.severity?.toLowerCase() === 'critical'
    )
    .slice(0, 5);

  // Recently updated: Acknowledged or Resolved
  const recentHistory = incidentList
    .filter((inc) => inc.status?.toLowerCase() !== 'triggered')
    .slice(0, 5);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <PageHeader
          title="Operations Dashboard"
          description="Live operational metrics, active incident queues, and responder activity."
        />

        <div className="flex items-center gap-2 text-xs text-slate-400 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-full">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" aria-hidden="true" />
          <span>Live Polling (15s)</span>
        </div>
      </div>

      {/* Primary KPI Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Active Outages */}
        <Link
          to="/incidents?active=true"
          className="group focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded-xl"
        >
          <Card className="hover:border-slate-700 transition-colors">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Active Incidents
                </p>
                <p className="text-2xl font-bold text-white mt-1">
                  {isLoading ? '—' : activeIncidents.length}
                </p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-indigo-950/80 border border-indigo-800/80 flex items-center justify-center text-indigo-400 group-hover:scale-105 transition-transform">
                <Activity className="w-5 h-5" aria-hidden="true" />
              </div>
            </div>
          </Card>
        </Link>

        {/* Critical Severity */}
        <Link
          to="/incidents?severity=critical&active=true"
          className="group focus:outline-none focus:ring-2 focus:ring-rose-500 rounded-xl"
        >
          <Card className="hover:border-rose-900/60 transition-colors">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-rose-400">
                  Critical Active
                </p>
                <p className="text-2xl font-bold text-rose-300 mt-1">
                  {isLoading ? '—' : criticalCount}
                </p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-rose-950/80 border border-rose-800/80 flex items-center justify-center text-rose-400 group-hover:scale-105 transition-transform">
                <AlertOctagon className="w-5 h-5" aria-hidden="true" />
              </div>
            </div>
          </Card>
        </Link>

        {/* Triggered (Unacknowledged) */}
        <Link
          to="/incidents?status=triggered"
          className="group focus:outline-none focus:ring-2 focus:ring-amber-500 rounded-xl"
        >
          <Card className="hover:border-amber-900/60 transition-colors">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-amber-400">
                  Triggered
                </p>
                <p className="text-2xl font-bold text-amber-300 mt-1">
                  {isLoading ? '—' : triggeredCount}
                </p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-amber-950/80 border border-amber-800/80 flex items-center justify-center text-amber-400 group-hover:scale-105 transition-transform">
                <BellRing className="w-5 h-5" aria-hidden="true" />
              </div>
            </div>
          </Card>
        </Link>

        {/* Acknowledged */}
        <Link
          to="/incidents?status=acknowledged"
          className="group focus:outline-none focus:ring-2 focus:ring-slate-500 rounded-xl"
        >
          <Card className="hover:border-slate-700 transition-colors">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Acknowledged
                </p>
                <p className="text-2xl font-bold text-slate-200 mt-1">
                  {isLoading ? '—' : acknowledgedCount}
                </p>
              </div>
              <div className="w-10 h-10 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300 group-hover:scale-105 transition-transform">
                <CheckCircle2 className="w-5 h-5" aria-hidden="true" />
              </div>
            </div>
          </Card>
        </Link>
      </div>

      {/* Needs Attention Queue */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-amber-400" aria-hidden="true" />
            <h3 className="text-sm font-semibold text-white">Needs Immediate Attention</h3>
            <span className="text-xs px-2 py-0.5 rounded-full bg-amber-950/80 border border-amber-800 text-amber-300 font-mono">
              {needsAttention.length}
            </span>
          </div>

          <Link
            to="/incidents?active=true"
            className="text-xs text-indigo-400 hover:text-indigo-300 inline-flex items-center gap-1 transition-colors"
          >
            View all active <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
          </Link>
        </div>

        <IncidentTable
          incidents={needsAttention}
          isLoading={isLoading}
          emptyMessage="All clear! No incidents need immediate attention."
          emptyDescription="There are currently no unacknowledged or critical active incidents."
        />
      </div>

      {/* Recently Updated or Resolved */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-300">Recently Updated or Resolved</h3>
          <Link
            to="/incidents"
            className="text-xs text-slate-400 hover:text-white inline-flex items-center gap-1 transition-colors"
          >
            View all incidents <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
          </Link>
        </div>

        <IncidentTable
          incidents={recentHistory}
          isLoading={isLoading}
          emptyMessage="No historical incidents"
          emptyDescription="Acknowledged and resolved incidents will be shown here."
        />
      </div>
    </div>
  );
};
