import React from 'react';
import { PageHeader } from '../components/shared/PageHeader';
import { Badge } from '../components/shared/Badge';
import { Card } from '../components/shared/Card';
import { LayoutDashboard } from 'lucide-react';

export const Dashboard: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="System overview, active incidents, and responder activity."
        badge={<Badge variant="info">Phase 7</Badge>}
      />

      <Card>
        <div className="flex flex-col items-center justify-center py-12 text-center max-w-md mx-auto space-y-3">
          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <LayoutDashboard className="w-6 h-6" aria-hidden="true" />
          </div>
          <h3 className="text-base font-semibold text-white">Operational Dashboard</h3>
          <p className="text-sm text-slate-400">
            Live operational metrics, active incident queues, and real-time responder summaries
            are scheduled for implementation in Phase 7.
          </p>
        </div>
      </Card>
    </div>
  );
};
