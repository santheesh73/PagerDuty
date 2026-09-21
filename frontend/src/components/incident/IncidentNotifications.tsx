import React from 'react';
import { useIncidentNotifications } from '../../hooks/useIncidents';
import { formatRelativeTime } from '../../lib/format';
import { Mail, MessageSquare, Globe, CheckCircle2, XCircle, Clock } from 'lucide-react';

export interface IncidentNotificationsProps {
  incidentId: number;
}

export const IncidentNotifications: React.FC<IncidentNotificationsProps> = ({ incidentId }) => {
  const { data: notifications = [], isLoading } = useIncidentNotifications(incidentId);

  if (isLoading) {
    return (
      <div className="border border-slate-800 rounded-xl p-4 bg-slate-900/40 space-y-2 animate-pulse">
        <div className="h-4 bg-slate-800 rounded w-1/3" />
        <div className="h-12 bg-slate-800/60 rounded" />
      </div>
    );
  }

  if (notifications.length === 0) {
    return null; // Don't take up space if no notifications were sent
  }

  const getChannelIcon = (channel: string) => {
    switch (channel.toLowerCase()) {
      case 'slack':
        return <MessageSquare className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />;
      case 'webhook':
        return <Globe className="w-3.5 h-3.5 text-indigo-400" aria-hidden="true" />;
      default:
        return <Mail className="w-3.5 h-3.5 text-amber-400" aria-hidden="true" />;
    }
  };

  const getStatusBadge = (status: string) => {
    const s = status.toLowerCase();
    if (s === 'delivered' || s === 'sent') {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/60">
          <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
          {status}
        </span>
      );
    }
    if (s === 'failed') {
      return (
        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-rose-400 bg-rose-950/60 px-2 py-0.5 rounded border border-rose-800/60">
          <XCircle className="w-3 h-3" aria-hidden="true" />
          Failed
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-slate-400 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
        <Clock className="w-3 h-3" aria-hidden="true" />
        {status}
      </span>
    );
  };

  return (
    <div className="border border-slate-800 rounded-xl p-4 bg-slate-900/40">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
          Notifications Dispatched ({notifications.length})
        </h4>
      </div>

      <div className="space-y-2">
        {notifications.map((n) => (
          <div
            key={n.id}
            className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800/80 text-xs"
          >
            <div className="flex items-center gap-2 min-w-0">
              {getChannelIcon(n.channel)}
              <span className="text-slate-200 truncate max-w-[130px]">
                {n.recipient_username || n.recipient_email || `User #${n.recipient}`}
              </span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {getStatusBadge(n.status)}
              <span className="text-[11px] text-slate-500">
                {formatRelativeTime(n.created_at)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
