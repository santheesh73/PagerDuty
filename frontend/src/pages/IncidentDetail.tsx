import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { useIncident, useIncidentEvents } from '../hooks/useIncidents';
import { StatusBadge } from '../components/shared/StatusBadge';
import { SeverityBadge } from '../components/shared/SeverityBadge';
import { Card } from '../components/shared/Card';
import { ErrorState } from '../components/shared/ErrorState';
import { IncidentActions } from '../components/incident/IncidentActions';
import { IncidentTimeline } from '../components/incident/IncidentTimeline';
import { IncidentNotifications } from '../components/incident/IncidentNotifications';
import { formatDateTime, formatRelativeTime, formatIncidentId } from '../lib/format';
import {
  ArrowLeft,
  Server,
  User,
  Fingerprint,
  Bell,
  Clock,
  CheckCircle,
  AlertTriangle,
  Layers,
  ShieldAlert,
} from 'lucide-react';

export const IncidentDetail: React.FC = () => {
  const { incidentId } = useParams<{ incidentId: string }>();

  const {
    data: incident,
    isLoading: incidentLoading,
    isError: incidentError,
    error,
    refetch: refetchIncident,
  } = useIncident(incidentId);

  const {
    data: events = [],
    isLoading: eventsLoading,
  } = useIncidentEvents(incidentId);

  const backLink = (
    <div className="mb-4">
      <Link
        to="/incidents"
        className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
        Back to Incidents
      </Link>
    </div>
  );

  if (incidentLoading) {
    return (
      <div className="space-y-6">
        {backLink}
        <div className="space-y-6 animate-pulse">
          <div className="h-4 bg-slate-800 rounded w-24" />
          <div className="h-10 bg-slate-800 rounded w-1/2" />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-4">
              <div className="h-40 bg-slate-800/60 rounded-xl" />
              <div className="h-96 bg-slate-800/40 rounded-xl" />
            </div>
            <div className="space-y-4">
              <div className="h-48 bg-slate-800/60 rounded-xl" />
              <div className="h-48 bg-slate-800/60 rounded-xl" />
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (incidentError || !incident) {
    return (
      <div className="space-y-4">
        {backLink}
        <ErrorState
          title="Incident Not Found"
          message={
            error instanceof Error
              ? error.message
              : `${formatIncidentId(incidentId)} could not be located or has been removed.`
          }
          onRetry={() => refetchIncident()}
        />
      </div>
    );
  }

  const responderName = incident.assigned_user
    ? incident.assigned_user.name || incident.assigned_user.email
    : 'Unassigned';

  return (
    <div className="space-y-6">
      {/* Top Back Navigation */}
      {backLink}

      {/* Main Header Card */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-6">
          <div className="space-y-2 max-w-3xl">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="font-mono text-sm font-semibold text-slate-300 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded">
                {formatIncidentId(incident.id)}
              </span>
              <SeverityBadge severity={incident.severity} />
              <StatusBadge status={incident.status} />
              {incident.status?.toLowerCase() === 'triggered' && (
                <span className="text-[11px] font-medium text-rose-400 bg-rose-950/70 border border-rose-800/80 px-2 py-0.5 rounded-full animate-pulse">
                  Active Escalation (5s poll)
                </span>
              )}
            </div>

            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight">
              {incident.title}
            </h1>

            <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 pt-1">
              <span className="inline-flex items-center gap-1.5" title={formatDateTime(incident.triggered_at)}>
                <Clock className="w-3.5 h-3.5 text-slate-500" aria-hidden="true" />
                Triggered {formatRelativeTime(incident.triggered_at)}
              </span>

              {incident.acknowledged_at && (
                <span className="inline-flex items-center gap-1.5" title={formatDateTime(incident.acknowledged_at)}>
                  <CheckCircle className="w-3.5 h-3.5 text-amber-500" aria-hidden="true" />
                  Acknowledged {formatRelativeTime(incident.acknowledged_at)}
                </span>
              )}

              {incident.resolved_at && (
                <span className="inline-flex items-center gap-1.5" title={formatDateTime(incident.resolved_at)}>
                  <CheckCircle className="w-3.5 h-3.5 text-emerald-500" aria-hidden="true" />
                  Resolved {formatRelativeTime(incident.resolved_at)}
                </span>
              )}
            </div>
          </div>

          {/* Action Buttons Bar */}
          <div className="shrink-0 pt-1">
            <IncidentActions incident={incident} />
          </div>
        </div>
      </div>

      {/* 2-Column Responsive Workspace Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left / Primary Column (2 cols) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Incident Attributes Card */}
          <Card>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-4">
              Incident Context & Attributes
            </h3>

            <dl className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <dt className="text-slate-500 flex items-center gap-1.5 mb-1">
                  <Server className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                  Affected Service
                </dt>
                <dd className="font-semibold text-slate-200">
                  {incident.service?.name || `Service #${incident.service?.id}`}
                </dd>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <dt className="text-slate-500 flex items-center gap-1.5 mb-1">
                  <ShieldAlert className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                  Escalation Tier
                </dt>
                <dd className="font-semibold text-indigo-300">
                  {incident.current_escalation_level ? `Level ${incident.current_escalation_level}` : 'Direct Routing'}
                </dd>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <dt className="text-slate-500 flex items-center gap-1.5 mb-1">
                  <Bell className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                  Grouped Alerts
                </dt>
                <dd className="font-mono font-semibold text-slate-200">
                  {incident.alert_count} {incident.alert_count === 1 ? 'alert' : 'alerts'} deduplicated
                </dd>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 sm:col-span-3">
                <dt className="text-slate-500 flex items-center gap-1.5 mb-1">
                  <Fingerprint className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
                  Deterministic Triage Fingerprint
                </dt>
                <dd className="font-mono text-slate-300 break-all select-all text-[11px]">
                  {incident.fingerprint}
                </dd>
              </div>
            </dl>
          </Card>

          {/* Chronological Audit Timeline */}
          <Card>
            <IncidentTimeline events={events} isLoading={eventsLoading} />
          </Card>
        </div>

        {/* Right / Sidebar Column (1 col) */}
        <div className="space-y-6">
          {/* Assigned Responder Card */}
          <Card>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
              <User className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
              Assigned Responder
            </h3>

            {incident.assigned_user ? (
              <div className="flex items-start gap-3 p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <div className="w-9 h-9 rounded-full bg-indigo-950 border border-indigo-800 flex items-center justify-center text-indigo-300 font-semibold text-xs shrink-0">
                  {(incident.assigned_user.name || incident.assigned_user.email).slice(0, 2).toUpperCase()}
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-semibold text-slate-200 truncate">
                    {responderName}
                  </p>
                  <p className="text-xs text-slate-400 truncate">
                    {incident.assigned_user.email}
                  </p>
                </div>
              </div>
            ) : (
              <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-800/60 text-xs text-amber-300 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" aria-hidden="true" />
                <span>No responder currently assigned. Schedule routing will assign when available.</span>
              </div>
            )}
          </Card>

          {/* Service Details Card */}
          <Card>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-slate-400" aria-hidden="true" />
              Service Information
            </h3>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Name</span>
                <span className="text-slate-200 font-medium">{incident.service?.name}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800/60">
                <span className="text-slate-400">Slug</span>
                <span className="font-mono text-slate-300">{incident.service?.slug}</span>
              </div>
              <div className="flex justify-between py-1">
                <span className="text-slate-400">Status</span>
                <span className="capitalize text-slate-200">{incident.service?.status || 'Active'}</span>
              </div>
            </div>
          </Card>

          {/* Dispatch Notifications Feed */}
          <IncidentNotifications incidentId={incident.id} />
        </div>
      </div>
    </div>
  );
};
