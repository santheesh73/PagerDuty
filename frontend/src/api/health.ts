import { apiClient } from './client';
import { HealthResponse } from '../types/health';

/**
 * Fetches the backend infrastructure health status.
 */
export async function getHealth(): Promise<HealthResponse> {
  return apiClient<HealthResponse>('/health/');
}
