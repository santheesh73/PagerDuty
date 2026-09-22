import { apiClient } from './client';
import { CreateServiceInput, Service, UpdateServiceInput } from '../types/service';

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

export const createService = async (data: CreateServiceInput): Promise<Service> => {
  return apiClient.post<Service>('/services/', data);
};

export const updateService = async (id: number, data: UpdateServiceInput): Promise<Service> => {
  return apiClient.patch<Service>(`/services/${id}/`, data);
};

