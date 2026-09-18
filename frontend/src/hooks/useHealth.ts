import { useQuery, UseQueryOptions } from '@tanstack/react-query';
import { getHealth } from '../api/health';
import { HealthResponse } from '../types/health';

export const HEALTH_QUERY_KEY = ['health'];

export function useHealth(
  options?: Partial<UseQueryOptions<HealthResponse, Error>>
) {
  return useQuery<HealthResponse, Error>({
    queryKey: HEALTH_QUERY_KEY,
    queryFn: getHealth,
    refetchInterval: 10000,
    ...options,
  });
}
