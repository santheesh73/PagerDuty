import React from 'react';
import { GitBranch, Plus, Shield, Users } from 'lucide-react';
import { EscalationPolicy } from '../../types/escalation';
import { Badge } from '../shared/Badge';
import { Button } from '../shared/Button';
import { EmptyState } from '../shared/EmptyState';

export interface PolicyListProps {
  policies: EscalationPolicy[];
  selectedPolicyId: number | null;
  onSelectPolicy: (policyId: number) => void;
  onCreatePolicy: () => void;
}

export const PolicyList: React.FC<PolicyListProps> = ({
  policies,
  selectedPolicyId,
  onSelectPolicy,
  onCreatePolicy,
}) => {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Escalation Policies ({policies.length})
        </h3>
        <Button size="sm" variant="secondary" onClick={onCreatePolicy}>
          <Plus className="w-3.5 h-3.5 mr-1" />
          New Policy
        </Button>
      </div>

      {policies.length === 0 ? (
        <EmptyState
          title="No policies"
          description="No escalation policies configured yet."
          action={
            <Button size="sm" variant="primary" onClick={onCreatePolicy}>
              Create First Policy
            </Button>
          }
        />
      ) : (
        <div className="space-y-2">
          {policies.map((policy) => {
            const isSelected = policy.id === selectedPolicyId;
            return (
              <div
                key={policy.id}
                role="button"
                tabIndex={0}
                onClick={() => onSelectPolicy(policy.id)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onSelectPolicy(policy.id);
                  }
                }}
                data-testid={`policy-item-${policy.id}`}
                className={`w-full text-left p-3.5 rounded-xl border transition-all cursor-pointer ${
                  isSelected
                    ? 'bg-indigo-950/30 border-indigo-500 shadow-sm'
                    : 'bg-slate-900 border-slate-800 hover:border-slate-700 hover:bg-slate-800/40'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                        isSelected
                          ? 'bg-indigo-600 text-white'
                          : 'bg-slate-800 text-slate-300'
                      }`}
                    >
                      <GitBranch className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-sm font-semibold text-white">{policy.name}</h4>
                      <p className="text-xs text-slate-400 font-mono">{policy.slug}</p>
                    </div>
                  </div>
                  <Badge variant={policy.is_active ? 'success' : 'neutral'}>
                    {policy.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>

                <div className="flex items-center gap-3 mt-3 pt-2.5 border-t border-slate-800/60 text-xs text-slate-400">
                  <span className="flex items-center gap-1">
                    <Users className="w-3.5 h-3.5 text-slate-500" />
                    {policy.team_name || `Team #${policy.team}`}
                  </span>
                  <span className="flex items-center gap-1">
                    <Shield className="w-3.5 h-3.5 text-slate-500" />
                    {policy.levels?.length ?? 0} level{policy.levels?.length === 1 ? '' : 's'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
