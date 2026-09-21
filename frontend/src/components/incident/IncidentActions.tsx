import React, { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Incident } from '../../types/incident';
import { ApiError } from '../../api/client';
import { queryKeys } from '../../app/queryClient';
import {
  useAcknowledgeIncident,
  useResolveIncident,
  useReopenIncident,
} from '../../hooks/useIncidents';
import { CheckCircle2, CheckCheck, RotateCcw, AlertTriangle, X } from 'lucide-react';

export interface IncidentActionsProps {
  incident: Incident;
  onActionSuccess?: () => void;
}

export const IncidentActions: React.FC<IncidentActionsProps> = ({
  incident,
  onActionSuccess,
}) => {
  const queryClient = useQueryClient();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isConflict, setIsConflict] = useState(false);

  const acknowledgeMutation = useAcknowledgeIncident();
  const resolveMutation = useResolveIncident();
  const reopenMutation = useReopenIncident();

  const isPending =
    acknowledgeMutation.isPending ||
    resolveMutation.isPending ||
    reopenMutation.isPending;

  const status = incident.status?.toLowerCase();
  const isTriggered = status === 'triggered';
  const isAcknowledged = status === 'acknowledged';
  const isResolved = status === 'resolved';

  const handleError = (error: unknown) => {
    let msg = 'Failed to update incident state.';
    let conflict = false;

    if (error instanceof ApiError) {
      msg = error.message;
      conflict = error.status === 409;
    } else if (error instanceof Error) {
      msg = error.message;
      conflict = error.message.includes('409') || error.message.toLowerCase().includes('conflict');
    }

    setErrorMessage(msg);
    setIsConflict(conflict);

    // When 409 or any error occurs, synchronize client cache with the authoritative backend state
    queryClient.invalidateQueries({ queryKey: queryKeys.incident(incident.id) });
    queryClient.invalidateQueries({ queryKey: ['incidents'] });
    queryClient.invalidateQueries({ queryKey: queryKeys.incidentEvents(incident.id) });
  };

  const handleAcknowledge = () => {
    setErrorMessage(null);
    setIsConflict(false);
    acknowledgeMutation.mutate(incident.id, {
      onSuccess: () => {
        onActionSuccess?.();
      },
      onError: handleError,
    });
  };

  const handleResolve = () => {
    setErrorMessage(null);
    setIsConflict(false);
    resolveMutation.mutate(incident.id, {
      onSuccess: () => {
        onActionSuccess?.();
      },
      onError: handleError,
    });
  };

  const handleReopen = () => {
    setErrorMessage(null);
    setIsConflict(false);
    reopenMutation.mutate(incident.id, {
      onSuccess: () => {
        onActionSuccess?.();
      },
      onError: handleError,
    });
  };

  return (
    <div className="space-y-3">
      {/* Error / Conflict Alert Banner */}
      {errorMessage && (
        <div
          role="alert"
          className={`p-3 rounded-lg border text-xs flex items-start justify-between gap-2 ${
            isConflict
              ? 'bg-amber-950/60 border-amber-800 text-amber-200'
              : 'bg-rose-950/60 border-rose-800 text-rose-200'
          }`}
        >
          <div className="flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
            <div>
              <p className="font-medium">
                {isConflict ? 'State Conflict Detected' : 'Action Failed'}
              </p>
              <p className="text-slate-300 mt-0.5">{errorMessage}</p>
              {isConflict && (
                <p className="text-slate-400 text-[11px] mt-1">
                  The latest server state has been refreshed.
                </p>
              )}
            </div>
          </div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-slate-400 hover:text-white p-1 rounded transition-colors"
            aria-label="Dismiss error"
          >
            <X className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        </div>
      )}

      {/* Action Buttons Group */}
      <div className="flex flex-wrap items-center gap-2.5">
        {/* Acknowledge Button */}
        <button
          type="button"
          disabled={!isTriggered || isPending}
          onClick={handleAcknowledge}
          className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-950 focus:ring-amber-500 disabled:opacity-40 disabled:pointer-events-none ${
            isTriggered
              ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-sm hover:shadow-amber-500/20'
              : 'bg-slate-800 text-slate-400 border border-slate-700'
          }`}
        >
          <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
          {acknowledgeMutation.isPending
            ? 'Acknowledging...'
            : isAcknowledged
            ? 'Acknowledged'
            : 'Acknowledge'}
        </button>

        {/* Resolve Button */}
        <button
          type="button"
          disabled={isResolved || isPending}
          onClick={handleResolve}
          className={`inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-950 focus:ring-emerald-500 disabled:opacity-40 disabled:pointer-events-none ${
            !isResolved
              ? 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-sm hover:shadow-emerald-500/20'
              : 'bg-slate-800 text-slate-400 border border-slate-700'
          }`}
        >
          <CheckCheck className="w-4 h-4" aria-hidden="true" />
          {resolveMutation.isPending
            ? 'Resolving...'
            : isResolved
            ? 'Resolved'
            : 'Resolve'}
        </button>

        {/* Reopen Button (shown only when resolved) */}
        {isResolved && (
          <button
            type="button"
            disabled={isPending}
            onClick={handleReopen}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider bg-rose-600 hover:bg-rose-500 text-white shadow-sm hover:shadow-rose-500/20 transition-all focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-slate-950 focus:ring-rose-500 disabled:opacity-40 disabled:pointer-events-none"
          >
            <RotateCcw className="w-4 h-4" aria-hidden="true" />
            {reopenMutation.isPending ? 'Reopening...' : 'Reopen Incident'}
          </button>
        )}
      </div>
    </div>
  );
};
