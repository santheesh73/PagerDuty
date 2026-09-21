import React from 'react';
import { PageHeader } from '../components/shared/PageHeader';
import { Badge } from '../components/shared/Badge';
import { Card } from '../components/shared/Card';
import { BarChart3 } from 'lucide-react';

export const Analytics: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Mean Time to Acknowledge (MTTA), Mean Time to Resolve (MTTR), and alert trends."
        badge={<Badge variant="info">Phase 8</Badge>}
      />

      <Card>
        <div className="flex flex-col items-center justify-center py-12 text-center max-w-md mx-auto space-y-3">
          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <BarChart3 className="w-6 h-6" aria-hidden="true" />
          </div>
          <h3 className="text-base font-semibold text-white">Incident Analytics & Reporting</h3>
          <p className="text-sm text-slate-400">
            MTTA/MTTR calculations, alert volume analytics, and responder workload insights
            are scheduled for Phase 8.
          </p>
        </div>
      </Card>
    </div>
  );
};
