import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Incident } from '../../types/incident';
import { StatusBadge } from '../shared/StatusBadge';
import { SeverityBadge } from '../shared/SeverityBadge';
import { formatRelativeTime, formatDateTime } from '../../lib/format';
import { AlertCircle, User, Bell, ChevronRight } from 'lucide-react';

export interface IncidentTableProps {
  incidents: Incident[];
  isLoading?: boolean;
  emptyMessage?: string;
  emptyDescription?: string;
}

export const IncidentTable: React.FC<IncidentTableProps> = ({
  incidents,
  isLoading = false,
  emptyMessage = 'No incidents found',
  emptyDescription = 'No operational incidents match the current filters.',
}) => {
  const navigate = useNavigate();

  if (isLoading) {
    return (
      <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/40">
        <div className="divide-y divide-slate-800/80">
          {[1, 2, 3, 4, 5].map((idx) => (
            <div key={idx} className="p-4 flex items-center justify-between animate-pulse">
              <div className="flex items-center gap-4 flex-1">
                <div className="w-12 h-5 bg-slate-800 rounded" />
                <div className="w-16 h-5 bg-slate-800 rounded" />
                <div className="w-20 h-5 bg-slate-800 rounded-full" />
                <div className="w-48 h-5 bg-slate-800 rounded" />
              </div>
              <div className="w-24 h-5 bg-slate-800 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (incidents.length === 0) {
    return (
      <div className="border border-slate-800/80 rounded-xl bg-slate-900/30 p-12 text-center">
        <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 mx-auto flex items-center justify-center text-slate-400 mb-3">
          <AlertCircle className="w-6 h-6" aria-hidden="true" />
        </div>
        <h3 className="text-sm font-semibold text-slate-200">{emptyMessage}</h3>
        <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">{emptyDescription}</p>
      </div>
    );
  }

  return (
    <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-900/40 shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-300 border-collapse">
          <thead>
            <tr className="border-b border-slate-800 bg-slate-900/90 text-xs font-semibold uppercase tracking-wider text-slate-400 select-none">
              <th scope="col" className="py-3 px-4 w-16">ID</th>
              <th scope="col" className="py-3 px-4 w-28">Severity</th>
              <th scope="col" className="py-3 px-4 w-32">Status</th>
              <th scope="col" className="py-3 px-4 min-w-[200px]">Title</th>
              <th scope="col" className="py-3 px-4 min-w-[140px]">Service</th>
              <th scope="col" className="py-3 px-4 min-w-[140px]">Assignee</th>
              <th scope="col" className="py-3 px-4 w-20 text-center">Alerts</th>
              <th scope="col" className="py-3 px-4 w-32 text-right">Triggered</th>
              <th scope="col" className="py-3 px-3 w-10"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/80">
            {incidents.map((incident) => {
              const responderName = incident.assigned_user
                ? incident.assigned_user.name || incident.assigned_user.email
                : 'Unassigned';

              return (
                <tr
                  key={incident.id}
                  onClick={() => navigate(`/incidents/${incident.id}`)}
                  className="hover:bg-slate-800/50 cursor-pointer transition-colors group focus-within:bg-slate-800/60"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      navigate(`/incidents/${incident.id}`);
                    }
                  }}
                  role="row"
                  aria-label={`Incident ${incident.id}: ${incident.title}`}
                >
                  <td className="py-3.5 px-4 font-mono text-xs font-medium text-slate-400 group-hover:text-indigo-400 transition-colors">
                    #{incident.id}
                  </td>
                  <td className="py-3.5 px-4">
                    <SeverityBadge severity={incident.severity} />
                  </td>
                  <td className="py-3.5 px-4">
                    <StatusBadge status={incident.status} />
                  </td>
                  <td className="py-3.5 px-4 font-medium text-slate-100 group-hover:text-white">
                    <span className="line-clamp-1">{incident.title}</span>
                  </td>
                  <td className="py-3.5 px-4 text-xs">
                    <span className="inline-flex items-center px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700/80 max-w-[180px] truncate">
                      {incident.service?.name || `Service #${incident.service?.id}`}
                    </span>
                  </td>
                  <td className="py-3.5 px-4 text-xs">
                    <div className="flex items-center gap-1.5 text-slate-300 truncate max-w-[160px]">
                      <User className="w-3.5 h-3.5 text-slate-500 shrink-0" aria-hidden="true" />
                      <span className={incident.assigned_user ? 'text-slate-200' : 'text-slate-500 italic'}>
                        {responderName}
                      </span>
                    </div>
                  </td>
                  <td className="py-3.5 px-4 text-center">
                    <span className="inline-flex items-center gap-1 text-xs font-mono text-slate-400">
                      <Bell className="w-3 h-3 text-slate-500" aria-hidden="true" />
                      {incident.alert_count}
                    </span>
                  </td>
                  <td
                    className="py-3.5 px-4 text-right text-xs text-slate-400 whitespace-nowrap"
                    title={formatDateTime(incident.triggered_at)}
                  >
                    {formatRelativeTime(incident.triggered_at)}
                  </td>
                  <td className="py-3.5 px-3 text-right text-slate-600 group-hover:text-slate-300 transition-colors">
                    <ChevronRight className="w-4 h-4 inline" aria-hidden="true" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
