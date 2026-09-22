import React from 'react';
import {
  ArrowDown,
  ArrowUp,
  Clock,
  Edit2,
  Plus,
  Shield,
  Trash2,
  User as UserIcon,
} from 'lucide-react';
import { EscalationPolicy } from '../../types/escalation';
import { Badge } from '../shared/Badge';
import { Button } from '../shared/Button';
import { Card } from '../shared/Card';
import { EmptyState } from '../shared/EmptyState';

export interface PolicyDetailProps {
  policy: EscalationPolicy;
  onEditPolicy: () => void;
  onAddLevel: () => void;
  onDeleteLevel: (levelId: number) => void;
  onReorderLevels: (levelIds: number[]) => void;
  isReordering?: boolean;
}

export const PolicyDetail: React.FC<PolicyDetailProps> = ({
  policy,
  onEditPolicy,
  onAddLevel,
  onDeleteLevel,
  onReorderLevels,
  isReordering = false,
}) => {
  // Sort levels strictly by order ascending
  const levels = [...(policy.levels || [])].sort((a, b) => a.order - b.order);

  const handleMoveUp = (index: number) => {
    if (index <= 0 || isReordering) return;
    const newLevels = [...levels];
    const temp = newLevels[index - 1];
    newLevels[index - 1] = newLevels[index];
    newLevels[index] = temp;
    onReorderLevels(newLevels.map((l) => l.id));
  };

  const handleMoveDown = (index: number) => {
    if (index >= levels.length - 1 || isReordering) return;
    const newLevels = [...levels];
    const temp = newLevels[index + 1];
    newLevels[index + 1] = newLevels[index];
    newLevels[index] = temp;
    onReorderLevels(newLevels.map((l) => l.id));
  };

  return (
    <div className="space-y-6">
      <Card
        title={policy.name}
        subtitle={`Owning team: ${policy.team_name || `Team #${policy.team}`}`}
        action={
          <div className="flex items-center gap-2">
            <Badge variant={policy.is_active ? 'success' : 'neutral'}>
              {policy.is_active ? 'Active Policy' : 'Inactive'}
            </Badge>
            <Button variant="outline" size="sm" onClick={onEditPolicy}>
              <Edit2 className="w-3.5 h-3.5 mr-1" />
              Edit
            </Button>
          </div>
        }
      >
        <div className="flex flex-wrap items-center gap-4 text-xs text-slate-400 font-mono pt-1">
          <div>
            <span className="text-slate-500">Identifier: </span>
            <span className="text-slate-300">{policy.slug}</span>
          </div>
          <div>
            <span className="text-slate-500">Configured Steps: </span>
            <span className="text-slate-300">{levels.length}</span>
          </div>
        </div>
      </Card>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-semibold text-slate-100">Escalation Path</h3>
            <p className="text-xs text-slate-400">
              Deterministic sequence of notification targets and delay intervals.
            </p>
          </div>
          <Button variant="primary" size="sm" onClick={onAddLevel}>
            <Plus className="w-3.5 h-3.5 mr-1" />
            Add Escalation Step
          </Button>
        </div>

        {levels.length === 0 ? (
          <EmptyState
            title="No escalation steps"
            description="Incidents mapped to this policy will not notify any responders until steps are defined."
            action={
              <Button size="sm" variant="primary" onClick={onAddLevel}>
                Add Step 1
              </Button>
            }
          />
        ) : (
          <div className="relative space-y-3">
            {levels.map((level, idx) => {
              const isCurrentOnCall = level.target_type === 'CURRENT_ON_CALL';
              const isFirst = idx === 0;
              const isLast = idx === levels.length - 1;

              return (
                <div
                  key={level.id}
                  data-testid={`level-card-${level.id}`}
                  className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl bg-slate-900 border border-slate-800 hover:border-slate-700 transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center text-indigo-300 font-semibold text-sm shrink-0">
                      {idx + 1}
                    </div>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                          Step {idx + 1}
                        </span>
                        {isCurrentOnCall ? (
                          <Badge variant="info">
                            <Shield className="w-3 h-3 mr-1" />
                            Current On-Call Responder
                          </Badge>
                        ) : (
                          <Badge variant="neutral">
                            <UserIcon className="w-3 h-3 mr-1" />
                            User: {level.target_username || `ID ${level.target_user}`}
                          </Badge>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 mt-1 text-xs text-slate-400">
                        <Clock className="w-3.5 h-3.5 text-slate-500" />
                        <span>
                          Notify responder. If unacknowledged, escalate after{' '}
                          <strong className="text-slate-200">{level.wait_minutes} min</strong>.
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1.5 self-end sm:self-auto">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleMoveUp(idx)}
                      disabled={isFirst || isReordering}
                      aria-label={`Move Step ${idx + 1} up`}
                      className="p-1.5 text-slate-400 hover:text-white"
                    >
                      <ArrowUp className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleMoveDown(idx)}
                      disabled={isLast || isReordering}
                      aria-label={`Move Step ${idx + 1} down`}
                      className="p-1.5 text-slate-400 hover:text-white"
                    >
                      <ArrowDown className="w-4 h-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onDeleteLevel(level.id)}
                      aria-label={`Delete Step ${idx + 1}`}
                      className="p-1.5 text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
