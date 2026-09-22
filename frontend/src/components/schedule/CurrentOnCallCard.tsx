import React from 'react';
import { ShieldCheck, UserX, Clock, Globe } from 'lucide-react';
import { OnCallResponse, Schedule } from '../../types/schedule';
import { Badge } from '../shared/Badge';
import { Card } from '../shared/Card';

export interface CurrentOnCallCardProps {
  schedule: Schedule;
  onCallData?: OnCallResponse;
  isLoading?: boolean;
}

export const CurrentOnCallCard: React.FC<CurrentOnCallCardProps> = ({
  schedule,
  onCallData,
  isLoading = false,
}) => {
  const user = onCallData?.user;
  const source = onCallData?.source;

  return (
    <Card
      title="Currently On-Call"
      subtitle={`Live responder calculation for ${schedule.name}`}
      action={
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 text-xs text-slate-400 font-mono">
            <Globe className="w-3.5 h-3.5 text-slate-500" />
            {schedule.timezone}
          </span>
          {schedule.is_primary && <Badge variant="info">Primary Schedule</Badge>}
        </div>
      }
      className="border-indigo-500/20 bg-gradient-to-b from-indigo-950/20 to-slate-900"
    >
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : user ? (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-xl bg-slate-950/50 border border-slate-800">
          <div className="flex items-center gap-3.5">
            <div className="w-12 h-12 rounded-full bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-300 font-semibold text-base shrink-0">
              {user.name ? user.name.charAt(0).toUpperCase() : user.username.charAt(0).toUpperCase()}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h4 className="text-base font-semibold text-white">{user.name || user.username}</h4>
                <span className="text-xs text-slate-400 font-mono">@{user.username}</span>
              </div>
              <div className="flex items-center gap-2 mt-1">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span className="text-xs text-slate-300">Active Incident Responder</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto">
            {source?.toUpperCase() === 'OVERRIDE' ? (
              <Badge variant="warning">
                Active Override
              </Badge>
            ) : source?.toUpperCase() === 'BASE' ? (
              <Badge variant="info">
                Standard Rotation
              </Badge>
            ) : (
              <Badge variant="neutral">Assigned</Badge>
            )}
            <div className="text-xs text-slate-500 font-mono flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span>Polled every 30s</span>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-3 p-4 rounded-xl bg-slate-950/40 border border-slate-800 text-slate-400">
          <UserX className="w-5 h-5 text-slate-500 shrink-0" />
          <div>
            <p className="text-sm font-medium text-slate-300">No responder currently on-call</p>
            <p className="text-xs text-slate-500 mt-0.5">
              There are no active shifts or overrides covering this time window in {schedule.timezone}.
            </p>
          </div>
        </div>
      )}
    </Card>
  );
};
