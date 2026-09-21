import React from 'react';
import { PageHeader } from '../components/shared/PageHeader';
import { Badge } from '../components/shared/Badge';
import { Card } from '../components/shared/Card';
import { GitBranch } from 'lucide-react';

export const EscalationPolicies: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Escalation Policies"
        description="Multi-tier incident escalation paths, delay timers, and responder fallbacks."
        badge={<Badge variant="info">Phase 8</Badge>}
      />

      <Card>
        <div className="flex flex-col items-center justify-center py-12 text-center max-w-md mx-auto space-y-3">
          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <GitBranch className="w-6 h-6" aria-hidden="true" />
          </div>
          <h3 className="text-base font-semibold text-white">Escalation Policy Editor</h3>
          <p className="text-sm text-slate-400">
            Multi-level escalation rules, wait minute configurations, and team-scoped policies
            are scheduled for Phase 8.
          </p>
        </div>
      </Card>
    </div>
  );
};
