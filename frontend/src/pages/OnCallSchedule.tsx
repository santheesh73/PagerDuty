import React, { useState } from 'react';
import { Plus, Users, Globe } from 'lucide-react';

import { CreateRotationInput, CreateScheduleInput } from '../types/schedule';
import {
  useCreateRotation,
  useCreateSchedule,
  useCurrentOnCall,
  useDeleteRotation,
  useScheduleRotations,
  useSchedules,
} from '../hooks/useSchedules';
import { useTeams, useUsers } from '../hooks/useTeams';
import { PageHeader } from '../components/shared/PageHeader';
import { Button } from '../components/shared/Button';
import { LoadingState } from '../components/shared/LoadingState';
import { ErrorState } from '../components/shared/ErrorState';
import { EmptyState } from '../components/shared/EmptyState';
import { CurrentOnCallCard } from '../components/schedule/CurrentOnCallCard';
import { RotationList } from '../components/schedule/RotationList';
import { RotationModal } from '../components/schedule/RotationModal';
import { ScheduleModal } from '../components/schedule/ScheduleModal';

export const OnCallSchedule: React.FC = () => {
  const [selectedScheduleId, setSelectedScheduleId] = useState<number | null>(null);
  const [scheduleModalOpen, setScheduleModalOpen] = useState(false);
  const [rotationModalOpen, setRotationModalOpen] = useState(false);
  const [rotationIsOverride, setRotationIsOverride] = useState(false);

  // Queries
  const { data: schedules = [], isLoading: schedulesLoading, isError, error, refetch } = useSchedules();
  const { data: teams = [] } = useTeams();
  const { data: users = [] } = useUsers();

  // Pick first schedule by default (prefer primary)
  const defaultScheduleId = schedules.find((s) => s.is_primary)?.id ?? schedules[0]?.id ?? null;
  const effectiveScheduleId = selectedScheduleId ?? defaultScheduleId;
  const activeSchedule = schedules.find((s) => s.id === effectiveScheduleId) || null;



  // Authoritative on-call query: polls every 30s
  const {
    data: onCallData,
    isLoading: onCallLoading,
  } = useCurrentOnCall(effectiveScheduleId ?? undefined, undefined, {
    refetchInterval: 30_000,
  });

  // Rotations query
  const {
    data: rotations = [],
    isLoading: rotationsLoading,
  } = useScheduleRotations(effectiveScheduleId ?? undefined);

  // Mutations
  const createScheduleMutation = useCreateSchedule();
  const createRotationMutation = useCreateRotation(effectiveScheduleId ?? 0);
  const deleteRotationMutation = useDeleteRotation(effectiveScheduleId ?? 0);


  const handleOpenAddShift = () => {
    setRotationIsOverride(false);
    setRotationModalOpen(true);
  };

  const handleOpenAddOverride = () => {
    setRotationIsOverride(true);
    setRotationModalOpen(true);
  };

  const handleCreateSchedule = async (data: CreateScheduleInput) => {
    const created = await createScheduleMutation.mutateAsync(data);
    setSelectedScheduleId(created.id);
  };

  const handleCreateRotation = async (data: CreateRotationInput) => {
    await createRotationMutation.mutateAsync(data);
  };

  const handleDeleteRotation = async (rotationId: number) => {
    if (window.confirm('Are you sure you want to remove this shift/override?')) {
      await deleteRotationMutation.mutateAsync(rotationId);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="On-Call Schedules"
        description="Shift rotations, active responder calculation, and temporary schedule overrides."
        actions={
          <Button variant="primary" onClick={() => setScheduleModalOpen(true)}>
            <Plus className="w-4 h-4 mr-1.5" />
            New Schedule
          </Button>
        }
      />

      {schedulesLoading ? (
        <LoadingState message="Loading on-call schedules..." />
      ) : isError ? (
        <ErrorState
          title="Failed to load schedules"
          message={error instanceof Error ? error.message : 'Unknown error occurred.'}
          onRetry={() => refetch()}
        />
      ) : schedules.length === 0 ? (
        <EmptyState
          title="No on-call schedules found"
          description="Create your first team on-call schedule to start assigning rotation shifts."
          action={
            <Button variant="primary" onClick={() => setScheduleModalOpen(true)}>
              <Plus className="w-4 h-4 mr-1.5" />
              Create First Schedule
            </Button>
          }
        />
      ) : (
        <div className="space-y-6">
          {/* Schedule Picker Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl bg-slate-900 border border-slate-800">
            <div className="flex items-center gap-3">
              <label htmlFor="schedule-select" className="text-xs font-semibold uppercase tracking-wider text-slate-400 shrink-0">
                Active Schedule:
              </label>
              <select
                id="schedule-select"
                value={effectiveScheduleId ?? ''}
                onChange={(e) => setSelectedScheduleId(Number(e.target.value))}
                className="px-3 py-1.5 bg-slate-800 border border-slate-700 rounded-lg text-sm text-slate-100 font-medium focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >

                {schedules.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name} ({s.team?.name || 'No Team'}{s.is_primary ? ' • Primary' : ''})
                  </option>
                ))}
              </select>
            </div>

            {activeSchedule && (
              <div className="flex items-center gap-4 text-xs text-slate-400">
                <span className="flex items-center gap-1 font-medium text-slate-300">
                  <Users className="w-3.5 h-3.5 text-slate-500" />
                  {activeSchedule.team?.name}
                </span>
                <span className="flex items-center gap-1 font-mono">
                  <Globe className="w-3.5 h-3.5 text-slate-500" />
                  {activeSchedule.timezone}
                </span>
              </div>
            )}
          </div>

          {activeSchedule && (
            <>
              {/* Authoritative Live On-Call Card */}
              <CurrentOnCallCard
                schedule={activeSchedule}
                onCallData={onCallData}
                isLoading={onCallLoading}
              />

              {/* Rotations and Overrides List */}
              {rotationsLoading ? (
                <LoadingState message="Loading rotation shifts..." />
              ) : (
                <RotationList
                  rotations={rotations}
                  onAddShift={handleOpenAddShift}
                  onAddOverride={handleOpenAddOverride}
                  onDelete={handleDeleteRotation}
                  isDeleting={deleteRotationMutation.isPending}
                />
              )}
            </>
          )}
        </div>
      )}

      {/* Schedule Create Modal */}
      <ScheduleModal
        isOpen={scheduleModalOpen}
        onClose={() => setScheduleModalOpen(false)}
        teams={teams}
        onSubmit={handleCreateSchedule}
        isLoading={createScheduleMutation.isPending}
      />

      {/* Rotation / Override Modal */}
      {effectiveScheduleId && (
        <RotationModal
          isOpen={rotationModalOpen}
          onClose={() => setRotationModalOpen(false)}
          scheduleId={effectiveScheduleId}

          initialIsOverride={rotationIsOverride}
          users={users}
          onSubmit={handleCreateRotation}
          isLoading={createRotationMutation.isPending}
        />
      )}
    </div>
  );
};
