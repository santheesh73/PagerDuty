import React from 'react';
import { ServiceIncidentCount } from '../../types/analytics';
import { Card } from '../shared/Card';
import { EmptyState } from '../shared/EmptyState';

export interface ServiceBreakdownProps {
  data?: ServiceIncidentCount[];
  isLoading?: boolean;
}

export const ServiceBreakdown: React.FC<ServiceBreakdownProps> = ({
  data = [],
  isLoading = false,
}) => {
  const maxCount = Math.max(...data.map((d) => d.count), 1);
  const totalCount = data.reduce((acc, curr) => acc + curr.count, 0);

  return (
    <Card
      title="Incidents by Service"
      subtitle="Operational service distribution across the selected time range"
    >
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : data.length === 0 ? (
        <EmptyState
          title="No incident activity"
          description="Zero incidents recorded for monitored services in this window."
        />
      ) : (
        <div className="space-y-3.5 pt-2">
          {data.map((item) => {
            const percentage = totalCount > 0 ? Math.round((item.count / totalCount) * 100) : 0;
            const barWidth = Math.round((item.count / maxCount) * 100);

            return (
              <div key={item.service_id} className="space-y-1.5" data-testid={`service-bar-${item.service_id}`}>
                <div className="flex items-center justify-between text-xs">
                  <span className="font-medium text-slate-200">{item.service_name}</span>
                  <div className="flex items-center gap-2 font-mono">
                    <span className="text-slate-400">{item.count} incident{item.count === 1 ? '' : 's'}</span>
                    <span className="text-slate-500">({percentage}%)</span>
                  </div>
                </div>

                <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-indigo-500 transition-all duration-500"
                    style={{ width: `${barWidth}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </Card>
  );
};
