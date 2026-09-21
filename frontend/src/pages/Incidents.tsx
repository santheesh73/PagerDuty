import React from 'react';
import { PageHeader } from '../components/shared/PageHeader';
import { Badge } from '../components/shared/Badge';
import { Card } from '../components/shared/Card';
import { AlertTriangle } from 'lucide-react';

export const Incidents: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Incidents"
        description="Filter, inspect, and manage active and historical operational incidents."
        badge={<Badge variant="info">Phase 7</Badge>}
      />

      <Card>
        <div className="flex flex-col items-center justify-center py-12 text-center max-w-md mx-auto space-y-3">
          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <AlertTriangle className="w-6 h-6" aria-hidden="true" />
          </div>
          <h3 className="text-base font-semibold text-white">Incident Workbench</h3>
          <p className="text-sm text-slate-400">
            Incident filtering by service, status, and severity, along with bulk management,
            will be implemented in Phase 7.
          </p>
        </div>
      </Card>
    </div>
  );
};
