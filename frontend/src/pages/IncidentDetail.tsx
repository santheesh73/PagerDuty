import React from 'react';
import { useParams, Link } from 'react-router-dom';
import { PageHeader } from '../components/shared/PageHeader';
import { Badge } from '../components/shared/Badge';
import { Card } from '../components/shared/Card';
import { ArrowLeft, Clock } from 'lucide-react';

export const IncidentDetail: React.FC = () => {
  const { incidentId } = useParams<{ incidentId: string }>();

  return (
    <div>
      <div className="mb-4">
        <Link
          to="/incidents"
          className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
          Back to Incidents
        </Link>
      </div>

      <PageHeader
        title={`Incident #${incidentId || 'Detail'}`}
        description="Detailed incident context, responder assignment, and chronological event timeline."
        badge={<Badge variant="info">Phase 7</Badge>}
      />

      <Card>
        <div className="flex flex-col items-center justify-center py-12 text-center max-w-md mx-auto space-y-3">
          <div className="w-12 h-12 rounded-xl bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-300">
            <Clock className="w-6 h-6" aria-hidden="true" />
          </div>
          <h3 className="text-base font-semibold text-white">Incident Timeline & Actions</h3>
          <p className="text-sm text-slate-400">
            Lifecycle actions (Acknowledge, Resolve, Reopen) and the immutable event timeline
            for Incident #{incidentId} are scheduled for Phase 7.
          </p>
        </div>
      </Card>
    </div>
  );
};
