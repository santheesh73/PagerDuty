import React from 'react';
import { PageHeader } from '../components/shared/PageHeader';
import { Badge } from '../components/shared/Badge';
import { Card } from '../components/shared/Card';
import { Layers } from 'lucide-react';

export const Services: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Services"
        description="Service catalog, team ownership, and integration endpoint configuration."
        badge={<Badge variant="info">Phase 8</Badge>}
      />

      <Card>
        <div className="flex flex-col items-center justify-center py-12 text-center max-w-md mx-auto space-y-3">
          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <Layers className="w-6 h-6" aria-hidden="true" />
          </div>
          <h3 className="text-base font-semibold text-white">Service Catalog</h3>
          <p className="text-sm text-slate-400">
            Operational service management, status indicators, and team ownership mapping
            are scheduled for implementation in Phase 8.
          </p>
        </div>
      </Card>
    </div>
  );
};
