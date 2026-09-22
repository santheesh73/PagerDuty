import React from 'react';
import { Calendar, Clock, Trash2, Zap, Shield, Plus } from 'lucide-react';
import { ScheduleRotation } from '../../types/schedule';
import { Badge } from '../shared/Badge';
import { Button } from '../shared/Button';
import { EmptyState } from '../shared/EmptyState';

export interface RotationListProps {
  rotations: ScheduleRotation[];
  onAddShift: () => void;
  onAddOverride: () => void;
  onDelete: (rotationId: number) => void;
  isDeleting?: boolean;
}

function formatDatetime(isoStr: string): string {
  try {
    const d = new Date(isoStr);
    return d.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  } catch {
    return isoStr;
  }
}

function calculateDurationHours(startIso: string, endIso: string): string {
  try {
    const start = new Date(startIso).getTime();
    const end = new Date(endIso).getTime();
    const diffMs = end - start;
    if (diffMs <= 0) return '0h';
    const hours = Math.round((diffMs / (1000 * 60 * 60)) * 10) / 10;
    if (hours < 24) return `${hours}h`;
    const days = Math.floor(hours / 24);
    const remHours = Math.round(hours % 24);
    return remHours > 0 ? `${days}d ${remHours}h` : `${days}d`;
  } catch {
    return '';
  }
}

export const RotationList: React.FC<RotationListProps> = ({
  rotations,
  onAddShift,
  onAddOverride,
  onDelete,
  isDeleting = false,
}) => {
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-semibold text-slate-100">Shifts & Overrides</h3>
          <p className="text-xs text-slate-400">
            Active rotation schedules and priority manual overrides.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={onAddShift}>
            <Plus className="w-3.5 h-3.5 mr-1" />
            Add Shift
          </Button>
          <Button variant="primary" size="sm" onClick={onAddOverride}>
            <Zap className="w-3.5 h-3.5 mr-1 text-amber-300" />
            Schedule Override
          </Button>
        </div>
      </div>

      {rotations.length === 0 ? (
        <EmptyState
          title="No shifts configured"
          description="There are currently no rotation shifts or overrides scheduled for this calendar."
          action={
            <div className="flex items-center gap-2 mt-2">
              <Button size="sm" variant="secondary" onClick={onAddShift}>
                Add First Shift
              </Button>
            </div>
          }
        />
      ) : (
        <div className="space-y-2.5">
          {rotations.map((rotation) => {
            const isOverride = rotation.is_override;
            const duration = calculateDurationHours(rotation.start_time, rotation.end_time);

            return (
              <div
                key={rotation.id}
                data-testid={`rotation-item-${rotation.id}`}
                className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl border transition-colors ${
                  isOverride
                    ? 'bg-amber-950/10 border-amber-500/30 hover:border-amber-500/50'
                    : 'bg-slate-900 border-slate-800 hover:border-slate-700'
                }`}
              >
                <div className="flex items-start sm:items-center gap-3">
                  <div
                    className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                      isOverride
                        ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                        : 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30'
                    }`}
                  >
                    {isOverride ? <Zap className="w-4 h-4" /> : <Shield className="w-4 h-4" />}
                  </div>

                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-white">
                        {rotation.user ? rotation.user.name || rotation.user.username : 'Unknown'}
                      </span>
                      {rotation.user?.username && (
                        <span className="text-xs text-slate-400 font-mono">
                          @{rotation.user.username}
                        </span>
                      )}
                      {isOverride ? (
                        <Badge variant="warning">Override</Badge>
                      ) : (
                        <Badge variant="info">Base Shift</Badge>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs text-slate-400">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5 text-slate-500" />
                        {formatDatetime(rotation.start_time)} → {formatDatetime(rotation.end_time)}
                      </span>
                      {duration && (
                        <span className="flex items-center gap-1 font-mono text-slate-500">
                          <Clock className="w-3 h-3" />
                          {duration}
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2 self-end sm:self-auto">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onDelete(rotation.id)}
                    disabled={isDeleting}
                    aria-label={`Delete shift for ${rotation.user?.username}`}
                    className="text-rose-400 hover:text-rose-300 hover:bg-rose-500/10"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
