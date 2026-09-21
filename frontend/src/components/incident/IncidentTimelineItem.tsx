import React, { useState } from 'react';
import { IncidentEvent } from '../../types/incident';
import { formatRelativeTime, formatDateTime } from '../../lib/format';
import {
  Bell,
  Layers,
  UserCheck,
  AlertTriangle,
  CheckCircle2,
  CheckCheck,
  RotateCcw,
  Zap,
  ChevronsUp,
  AlertOctagon,
  Info,
  ChevronDown,
  ChevronRight,
} from 'lucide-react';

export interface IncidentTimelineItemProps {
  event: IncidentEvent;
  isLast?: boolean;
}

interface EventVisualConfig {
  label: string;
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean | 'true' | 'false' }>;
  iconColor: string;
  badgeBg: string;
  borderColor: string;
}

function getEventConfig(eventType: string): EventVisualConfig {
  const normalized = eventType.toUpperCase();

  switch (normalized) {
    case 'INCIDENT_TRIGGERED':
    case 'INCIDENT_CREATED':
      return {
        label: 'Incident Triggered',
        icon: Bell,
        iconColor: 'text-rose-400',
        badgeBg: 'bg-rose-950/70',
        borderColor: 'border-rose-800/80',
      };
    case 'ALERT_ATTACHED':
      return {
        label: 'Alert Attached',
        icon: Layers,
        iconColor: 'text-indigo-400',
        badgeBg: 'bg-indigo-950/70',
        borderColor: 'border-indigo-800/80',
      };
    case 'RESPONDER_ASSIGNED':
      return {
        label: 'Responder Assigned',
        icon: UserCheck,
        iconColor: 'text-blue-400',
        badgeBg: 'bg-blue-950/70',
        borderColor: 'border-blue-800/80',
      };
    case 'ROUTING_UNAVAILABLE':
      return {
        label: 'Routing Unavailable',
        icon: AlertTriangle,
        iconColor: 'text-amber-400',
        badgeBg: 'bg-amber-950/70',
        borderColor: 'border-amber-800/80',
      };
    case 'INCIDENT_ACKNOWLEDGED':
      return {
        label: 'Incident Acknowledged',
        icon: CheckCircle2,
        iconColor: 'text-amber-400',
        badgeBg: 'bg-amber-950/70',
        borderColor: 'border-amber-800/80',
      };
    case 'INCIDENT_RESOLVED':
      return {
        label: 'Incident Resolved',
        icon: CheckCheck,
        iconColor: 'text-emerald-400',
        badgeBg: 'bg-emerald-950/70',
        borderColor: 'border-emerald-800/80',
      };
    case 'INCIDENT_REOPENED':
      return {
        label: 'Incident Reopened',
        icon: RotateCcw,
        iconColor: 'text-rose-400',
        badgeBg: 'bg-rose-950/70',
        borderColor: 'border-rose-800/80',
      };
    case 'ESCALATION_STARTED':
      return {
        label: 'Escalation Started',
        icon: Zap,
        iconColor: 'text-indigo-400',
        badgeBg: 'bg-indigo-950/70',
        borderColor: 'border-indigo-800/80',
      };
    case 'INCIDENT_ESCALATED':
      return {
        label: 'Incident Escalated',
        icon: ChevronsUp,
        iconColor: 'text-purple-400',
        badgeBg: 'bg-purple-950/70',
        borderColor: 'border-purple-800/80',
      };
    case 'ESCALATION_EXHAUSTED':
      return {
        label: 'Escalation Exhausted',
        icon: AlertOctagon,
        iconColor: 'text-rose-400',
        badgeBg: 'bg-rose-950/70',
        borderColor: 'border-rose-800/80',
      };
    case 'ESCALATION_TARGET_UNAVAILABLE':
      return {
        label: 'Escalation Target Unavailable',
        icon: AlertTriangle,
        iconColor: 'text-amber-400',
        badgeBg: 'bg-amber-950/70',
        borderColor: 'border-amber-800/80',
      };
    default: {
      // Graceful fallback for any unknown future event types
      const humanized = eventType
        .split('_')
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
        .join(' ');
      return {
        label: humanized,
        icon: Info,
        iconColor: 'text-slate-400',
        badgeBg: 'bg-slate-900',
        borderColor: 'border-slate-700',
      };
    }
  }
}

export const IncidentTimelineItem: React.FC<IncidentTimelineItemProps> = ({
  event,
  isLast = false,
}) => {
  const [showMetadata, setShowMetadata] = useState(false);
  const config = getEventConfig(event.event_type);
  const Icon = config.icon;

  const actorText = event.actor
    ? event.actor.name || event.actor.email
    : 'System / Automation';

  const hasMetadata =
    event.metadata &&
    typeof event.metadata === 'object' &&
    Object.keys(event.metadata).length > 0;

  return (
    <div className="relative flex gap-4 text-left group">
      {/* Timeline spine connector */}
      {!isLast && (
        <span
          className="absolute left-4 top-8 -bottom-2 w-0.5 bg-slate-800 group-hover:bg-slate-700 transition-colors"
          aria-hidden="true"
        />
      )}

      {/* Event Icon Bubble */}
      <div
        className={`relative z-10 w-8 h-8 rounded-full border flex items-center justify-center shrink-0 ${config.badgeBg} ${config.borderColor} shadow-sm`}
      >
        <Icon className={`w-4 h-4 ${config.iconColor}`} aria-hidden="true" />
      </div>

      {/* Event Content Box */}
      <div className="flex-1 pb-6">
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-xl p-3 hover:border-slate-700/80 transition-colors">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-200">
                {config.label}
              </span>
              <span className="text-xs text-slate-400">
                by <span className="text-slate-300 font-medium">{actorText}</span>
              </span>
            </div>

            <span
              className="text-xs text-slate-500 whitespace-nowrap cursor-default"
              title={formatDateTime(event.created_at)}
            >
              {formatRelativeTime(event.created_at)}
            </span>
          </div>

          {/* Quick metadata highlights */}
          {hasMetadata && (
            <div className="mt-2 pt-2 border-t border-slate-800/60 flex flex-wrap items-center gap-2 text-xs">
              {'level_number' in event.metadata && (
                <span className="px-2 py-0.5 rounded bg-purple-950/70 border border-purple-800 text-purple-300 text-[11px] font-medium">
                  Escalation Level {String(event.metadata.level_number)}
                </span>
              )}
              {'reason' in event.metadata && (
                <span className="text-slate-400 text-xs italic">
                  &ldquo;{String(event.metadata.reason)}&rdquo;
                </span>
              )}
              {'alert_id' in event.metadata && (
                <span className="px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-300 text-[11px] font-mono">
                  Alert #{String(event.metadata.alert_id)}
                </span>
              )}
              {'target_user' in event.metadata && (
                <span className="px-2 py-0.5 rounded bg-blue-950/70 border border-blue-800 text-blue-300 text-[11px]">
                  Target: {String(event.metadata.target_user)}
                </span>
              )}

              {/* Metadata Details Toggle */}
              <button
                type="button"
                onClick={() => setShowMetadata(!showMetadata)}
                className="inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-300 ml-auto transition-colors"
                aria-label={showMetadata ? 'Hide event payload' : 'Show event payload'}
              >
                {showMetadata ? (
                  <>
                    <ChevronDown className="w-3 h-3" aria-hidden="true" />
                    Hide raw
                  </>
                ) : (
                  <>
                    <ChevronRight className="w-3 h-3" aria-hidden="true" />
                    Inspect metadata
                  </>
                )}
              </button>
            </div>
          )}

          {/* Expanded raw JSON inspector */}
          {showMetadata && hasMetadata && (
            <div className="mt-2 p-2 rounded-lg bg-slate-950 border border-slate-800 overflow-x-auto">
              <pre className="text-[11px] font-mono text-slate-300">
                {JSON.stringify(event.metadata, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
