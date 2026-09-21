import React from 'react';
import { PageHeader } from '../components/shared/PageHeader';
import { Badge } from '../components/shared/Badge';
import { Card } from '../components/shared/Card';
import { Calendar } from 'lucide-react';

export const OnCallSchedule: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="On-call Schedules"
        description="Shift rotations, active responder calculation, and temporary schedule overrides."
        badge={<Badge variant="info">Phase 8</Badge>}
      />

      <Card>
        <div className="flex flex-col items-center justify-center py-12 text-center max-w-md mx-auto space-y-3">
          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <Calendar className="w-6 h-6" aria-hidden="true" />
          </div>
          <h3 className="text-base font-semibold text-white">Schedule Management</h3>
          <p className="text-sm text-slate-400">
            On-call calendar views, shift rotation management, and override scheduling
            are scheduled for Phase 8.
          </p>
        </div>
      </Card>
    </div>
  );
};
