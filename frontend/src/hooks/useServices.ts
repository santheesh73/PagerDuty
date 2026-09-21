import { useQuery } from '@tanstack/react-query';
import { Service } from '../types/service';
import { ServiceFilters, getServices } from '../api/services';
import { queryKeys } from '../app/queryClient';

export interface UseServicesOptions {
  enabled?: boolean;
}

/**
 * Hook to fetch services list (for filter dropdowns and service references).
 */
export function useServices(filters?: ServiceFilters, options?: UseServicesOptions) {
  return useQuery<Service[]>({
    queryKey: queryKeys.services(filters as Record<string, unknown>),
    queryFn: () => getServices(filters),
    staleTime: 60_000,
    enabled: options?.enabled ?? true,
  });
}
