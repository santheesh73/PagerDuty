import React from 'react';
import { IncidentTrendPoint } from '../../types/analytics';
import { Card } from '../shared/Card';
import { EmptyState } from '../shared/EmptyState';

export interface IncidentTrendChartProps {
  data?: IncidentTrendPoint[];
  isLoading?: boolean;
}

export const IncidentTrendChart: React.FC<IncidentTrendChartProps> = ({
  data = [],
  isLoading = false,
}) => {
  const maxCount = Math.max(...data.map((d) => d.count), 1);
  const totalIncidents = data.reduce((acc, curr) => acc + curr.count, 0);

  return (
    <Card
      title="Daily Incident Trend"
      subtitle="Incident creation volume across consecutive calendar days"
      action={
        <div className="font-mono text-xs text-slate-400">
          Total: <strong className="text-white">{totalIncidents}</strong>
        </div>
      }
    >
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : data.length === 0 ? (
        <EmptyState
          title="No trend data"
          description="No incidents recorded during this timeframe."
        />
      ) : (
        <div className="pt-4">
          <div className="flex items-end gap-1.5 h-44 w-full px-2 border-b border-slate-800 pb-2 overflow-x-auto">
            {data.map((point) => {
              const heightPercent = point.count === 0 ? 4 : Math.max(8, Math.round((point.count / maxCount) * 100));
              const dateLabel = point.date.slice(5); // MM-DD

              return (
                <div
                  key={point.date}
                  data-testid={`trend-bar-${point.date}`}
                  className="flex-1 min-w-[20px] flex flex-col items-center justify-end h-full group relative"
                >
                  {/* Tooltip on hover */}
                  <div className="absolute -top-9 hidden group-hover:flex flex-col items-center z-20 pointer-events-none">
                    <div className="px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs font-mono text-white whitespace-nowrap shadow-lg">
                      {point.date}: {point.count}
                    </div>
                    <div className="w-1.5 h-1.5 bg-slate-800 border-r border-b border-slate-700 rotate-45 -mt-1" />
                  </div>

                  {/* Bar */}
                  <div
                    className={`w-full rounded-t transition-all ${
                      point.count > 0
                        ? 'bg-indigo-600 group-hover:bg-indigo-500'
                        : 'bg-slate-800/60'
                    }`}
                    style={{ height: `${heightPercent}%` }}
                  />
                  <span className="text-[10px] text-slate-500 font-mono mt-1 rotate-45 origin-left truncate max-w-[28px]">
                    {dateLabel}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </Card>
  );
};
