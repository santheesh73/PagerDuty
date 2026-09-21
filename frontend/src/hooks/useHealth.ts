import { useQuery } from '@tanstack/react-query';
import { getHealth } from '../api/health';
import { queryKeys } from '../app/queryClient';
import { HealthResponse } from '../types/health';

export const useHealth = () => {
  return useQuery<HealthResponse, Error>({
    queryKey: queryKeys.health,
    queryFn: getHealth,
    staleTime: 10_000,
  });
};
