import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CreateRotationInput,
  CreateScheduleInput,
  OnCallResponse,
  Schedule,
  ScheduleRotation,
  UpdateRotationInput,
  UpdateScheduleInput,
} from '../types/schedule';
import {
  ScheduleFilters,
  createSchedule,
  createScheduleRotation,
  deleteScheduleRotation,
  getCurrentOnCall,
  getSchedule,
  getScheduleRotations,
  getSchedules,
  updateSchedule,
  updateScheduleRotation,
} from '../api/schedules';
import { queryKeys } from '../app/queryClient';

export function useSchedules(filters?: ScheduleFilters) {
  return useQuery<Schedule[]>({
    queryKey: queryKeys.schedules(filters as Record<string, unknown>),
    queryFn: () => getSchedules(filters),
    staleTime: 30_000,
  });
}

export function useSchedule(id?: number | string) {
  const numericId = id ? Number(id) : undefined;
  return useQuery<Schedule>({
    queryKey: queryKeys.schedule(numericId ?? 0),
    queryFn: () => getSchedule(numericId!),
    enabled: Boolean(numericId),
  });
}

export function useScheduleRotations(scheduleId?: number | string) {
  const numericId = scheduleId ? Number(scheduleId) : undefined;
  return useQuery<ScheduleRotation[]>({
    queryKey: queryKeys.scheduleRotations(numericId ?? 0),
    queryFn: () => getScheduleRotations(numericId!),
    enabled: Boolean(numericId),
    staleTime: 15_000,
  });
}

/**
 * Authoritative on-call hook.
 * Polls backend every 30 seconds by default.
 * Does NOT compute on-call client-side.
 */
export function useCurrentOnCall(
  scheduleId?: number | string,
  timestamp?: string,
  options?: { refetchInterval?: number | false }
) {
  const numericId = scheduleId ? Number(scheduleId) : undefined;
  return useQuery<OnCallResponse>({
    queryKey: queryKeys.currentOnCall(numericId ?? 0, timestamp),
    queryFn: () => getCurrentOnCall(numericId!, timestamp),
    enabled: Boolean(numericId),
    refetchInterval: options?.refetchInterval ?? 30_000,
    staleTime: 10_000,
  });
}

export function useCreateSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateScheduleInput) => createSchedule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] });
    },
  });
}

export function useUpdateSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateScheduleInput }) => updateSchedule(id, data),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['schedules'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.schedule(id) });
    },
  });
}

export function useCreateRotation(scheduleId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateRotationInput) => createScheduleRotation(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduleRotations(scheduleId) });
      queryClient.invalidateQueries({ queryKey: ['schedule', scheduleId, 'on-call'] });
    },
  });
}

export function useUpdateRotation(scheduleId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateRotationInput }) =>
      updateScheduleRotation(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduleRotations(scheduleId) });
      queryClient.invalidateQueries({ queryKey: ['schedule', scheduleId, 'on-call'] });
    },
  });
}

export function useDeleteRotation(scheduleId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteScheduleRotation(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.scheduleRotations(scheduleId) });
      queryClient.invalidateQueries({ queryKey: ['schedule', scheduleId, 'on-call'] });
    },
  });
}
