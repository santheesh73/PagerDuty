import { apiClient } from './client';
import { OnCallResponse, Schedule, ScheduleRotation } from '../types/schedule';

export interface ScheduleFilters {
  team?: number;
  is_active?: boolean;
  is_primary?: boolean;
}

export const getSchedules = async (filters?: ScheduleFilters): Promise<Schedule[]> => {
  return apiClient.get<Schedule[]>('/schedules/', { params: filters as Record<string, string | number | boolean> });
};

export const getSchedule = async (id: number): Promise<Schedule> => {
  return apiClient.get<Schedule>(`/schedules/${id}/`);
};

export const getScheduleRotations = async (scheduleId: number): Promise<ScheduleRotation[]> => {
  return apiClient.get<ScheduleRotation[]>('/schedule-rotations/', { params: { schedule: scheduleId } });
};

export const getCurrentOnCall = async (scheduleId: number, at?: string): Promise<OnCallResponse> => {
  return apiClient.get<OnCallResponse>(`/schedules/${scheduleId}/on-call/`, {
    params: at ? { at } : undefined,
  });
};
