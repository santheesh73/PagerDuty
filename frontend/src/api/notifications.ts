import { apiClient } from './client';
import { Notification } from '../types/notification';

export interface NotificationFilters {
  incident?: number;
  recipient?: number;
  status?: string;
}

export const getNotifications = async (
  filters?: NotificationFilters
): Promise<Notification[]> => {
  return apiClient.get<Notification[]>('/notifications/', {
    params: filters as Record<string, string | number | boolean>,
  });
};

export const getNotification = async (id: number): Promise<Notification> => {
  return apiClient.get<Notification>(`/notifications/${id}/`);
};

export const retryNotification = async (
  id: number
): Promise<{ message: string; notification_id: number }> => {
  return apiClient.post<{ message: string; notification_id: number }>(
    `/notifications/${id}/retry/`
  );
};
