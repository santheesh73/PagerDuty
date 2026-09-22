import { apiClient } from './client';
import {
  CreateRotationInput,
  CreateScheduleInput,
  OnCallResponse,
  Schedule,
  ScheduleRotation,
  UpdateRotationInput,
  UpdateScheduleInput,
} from '../types/schedule';

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

export const createSchedule = async (data: CreateScheduleInput): Promise<Schedule> => {
  return apiClient.post<Schedule>('/schedules/', data);
};

export const updateSchedule = async (id: number, data: UpdateScheduleInput): Promise<Schedule> => {
  return apiClient.patch<Schedule>(`/schedules/${id}/`, data);
};

export const getScheduleRotations = async (scheduleId: number): Promise<ScheduleRotation[]> => {
  return apiClient.get<ScheduleRotation[]>('/schedule-rotations/', { params: { schedule: scheduleId } });
};

export const createScheduleRotation = async (data: CreateRotationInput): Promise<ScheduleRotation> => {
  return apiClient.post<ScheduleRotation>('/schedule-rotations/', data);
};

export const updateScheduleRotation = async (
  id: number,
  data: UpdateRotationInput
): Promise<ScheduleRotation> => {
  return apiClient.patch<ScheduleRotation>(`/schedule-rotations/${id}/`, data);
};

export const deleteScheduleRotation = async (id: number): Promise<void> => {
  return apiClient.delete<void>(`/schedule-rotations/${id}/`);
};

export const getCurrentOnCall = async (scheduleId: number, at?: string): Promise<OnCallResponse> => {
  return apiClient.get<OnCallResponse>(`/schedules/${scheduleId}/on-call/`, {
    params: at ? { at } : undefined,
  });
};

