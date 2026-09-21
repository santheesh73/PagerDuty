import { apiClient } from './client';
import { Service } from '../types/service';

export interface ServiceFilters {
  team?: number;
  status?: string;
  is_active?: boolean;
}

export const getServices = async (filters?: ServiceFilters): Promise<Service[]> => {
  return apiClient.get<Service[]>('/services/', { params: filters as Record<string, string | number | boolean> });
};

export const getService = async (id: number): Promise<Service> => {
  return apiClient.get<Service>(`/services/${id}/`);
};
