import React, { useState } from 'react';
import { IncidentEvent } from '../../types/incident';
import { IncidentTimelineItem } from './IncidentTimelineItem';
import { ArrowDownUp, History } from 'lucide-react';

export interface IncidentTimelineProps {
  events: IncidentEvent[];
  isLoading?: boolean;
}

export const IncidentTimeline: React.FC<IncidentTimelineProps> = ({
  events,
  isLoading = false,
}) => {
  const [newestFirst, setNewestFirst] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-4 py-4 animate-pulse">
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex gap-4">
            <div className="w-8 h-8 rounded-full bg-slate-800 shrink-0" />
            <div className="flex-1 bg-slate-800/60 rounded-xl h-20" />
          </div>
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div className="border border-slate-800 rounded-xl bg-slate-900/30 p-8 text-center">
        <History className="w-8 h-8 text-slate-600 mx-auto mb-2" aria-hidden="true" />
        <h4 className="text-sm font-medium text-slate-300">No events recorded</h4>
        <p className="text-xs text-slate-500 mt-1">
          Audit timeline events will appear here as the incident progresses.
        </p>
      </div>
    );
  }

  const sortedEvents = [...events].sort((a, b) => {
    const timeA = new Date(a.created_at).getTime();
    const timeB = new Date(b.created_at).getTime();
    return newestFirst ? timeB - timeA : timeA - timeB;
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-slate-200">Incident Timeline</h3>
          <span className="px-2 py-0.5 text-xs rounded-full bg-slate-800 text-slate-400 font-mono">
            {events.length}
          </span>
        </div>

        <button
          type="button"
          onClick={() => setNewestFirst(!newestFirst)}
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white px-2.5 py-1 rounded-lg hover:bg-slate-800 transition-colors"
          title="Toggle sort order"
        >
          <ArrowDownUp className="w-3.5 h-3.5" aria-hidden="true" />
          <span>{newestFirst ? 'Newest first' : 'Oldest first'}</span>
        </button>
      </div>

      <div className="pt-2">
        {sortedEvents.map((event, index) => (
          <IncidentTimelineItem
            key={event.id}
            event={event}
            isLast={index === sortedEvents.length - 1}
          />
        ))}
      </div>
    </div>
  );
};
