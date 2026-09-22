import React from 'react';
import { Edit2, ShieldAlert, CheckCircle2, AlertTriangle, Wrench } from 'lucide-react';
import { Service, ServiceStatus } from '../../types/service';
import { Badge } from '../shared/Badge';
import { Button } from '../shared/Button';
import { EmptyState } from '../shared/EmptyState';

export interface ServiceTableProps {
  services: Service[];
  onEdit: (service: Service) => void;
}

const statusConfig: Record<
  ServiceStatus,
  { label: string; badgeVariant: 'success' | 'warning' | 'error' | 'info'; icon: React.FC<{ className?: string }> }
> = {
  HEALTHY: { label: 'Healthy', badgeVariant: 'success', icon: CheckCircle2 },
  DEGRADED: { label: 'Degraded', badgeVariant: 'warning', icon: AlertTriangle },
  DOWN: { label: 'Down', badgeVariant: 'error', icon: ShieldAlert },
  MAINTENANCE: { label: 'Maintenance', badgeVariant: 'info', icon: Wrench },
};


export const ServiceTable: React.FC<ServiceTableProps> = ({ services, onEdit }) => {
  if (services.length === 0) {
    return (
      <EmptyState
        title="No services found"
        description="No services match your filters. Create a new service or adjust your query."
      />
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900 shadow-sm">
      <table className="w-full text-left text-sm text-slate-300">
        <thead className="border-b border-slate-800 bg-slate-950/50 text-xs uppercase tracking-wider text-slate-400">
          <tr>
            <th scope="col" className="py-3.5 px-4 font-semibold">Service Name</th>
            <th scope="col" className="py-3.5 px-4 font-semibold">Status</th>
            <th scope="col" className="py-3.5 px-4 font-semibold">Team</th>
            <th scope="col" className="py-3.5 px-4 font-semibold">Escalation Policy</th>
            <th scope="col" className="py-3.5 px-4 font-semibold">State</th>
            <th scope="col" className="py-3.5 px-4 text-right font-semibold">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-800/60 font-normal">
          {services.map((service) => {
            const statusInfo = statusConfig[service.status] || {
              label: service.status,
              badgeVariant: 'info',
              icon: ShieldAlert,
            };
            const StatusIcon = statusInfo.icon;

            return (
              <tr
                key={service.id}
                className="hover:bg-slate-800/40 transition-colors"
                data-testid={`service-row-${service.id}`}
              >
                <td className="py-3.5 px-4">
                  <div className="font-medium text-white">{service.name}</div>
                  <div className="text-xs text-slate-400 font-mono mt-0.5">{service.slug}</div>
                  {service.description && (
                    <p className="text-xs text-slate-500 mt-1 line-clamp-1">{service.description}</p>
                  )}
                </td>
                <td className="py-3.5 px-4">
                  <div className="inline-flex items-center gap-1.5">
                    <StatusIcon className="w-4 h-4 text-slate-400 shrink-0" />
                    <Badge variant={statusInfo.badgeVariant}>{statusInfo.label}</Badge>
                  </div>
                </td>
                <td className="py-3.5 px-4 text-slate-300">
                  {service.team ? (
                    <span className="font-medium text-slate-200">{service.team.name}</span>
                  ) : (
                    <span className="text-slate-500 italic">Unassigned</span>
                  )}
                </td>
                <td className="py-3.5 px-4">
                  {service.escalation_policy ? (
                    <span className="inline-flex items-center text-xs font-mono px-2 py-1 rounded bg-slate-800 text-indigo-300 border border-slate-700">
                      {service.escalation_policy.name}
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500 italic">Default</span>
                  )}
                </td>
                <td className="py-3.5 px-4">
                  <Badge variant={service.is_active ? 'success' : 'neutral'}>
                    {service.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </td>
                <td className="py-3.5 px-4 text-right">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onEdit(service)}
                    aria-label={`Edit ${service.name}`}
                  >
                    <Edit2 className="w-3.5 h-3.5 mr-1" />
                    Edit
                  </Button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};
