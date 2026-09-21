import { apiClient } from './client';
import { HealthResponse } from '../types/health';

export const getHealth = async (): Promise<HealthResponse> => {
  return apiClient.get<HealthResponse>('/health/');
};
