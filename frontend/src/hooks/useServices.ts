import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CreateServiceInput, Service, UpdateServiceInput } from '../types/service';
import {
  ServiceFilters,
  createService,
  getService,
  getServices,
  updateService,
} from '../api/services';
import { queryKeys } from '../app/queryClient';

export interface UseServicesOptions {
  enabled?: boolean;
}

/**
 * Hook to fetch services list (for filter dropdowns, tables, and service references).
 */
export function useServices(filters?: ServiceFilters, options?: UseServicesOptions) {
  return useQuery<Service[]>({
    queryKey: queryKeys.services(filters as Record<string, unknown>),
    queryFn: () => getServices(filters),
    staleTime: 60_000,
    enabled: options?.enabled ?? true,
  });
}

/**
 * Hook to fetch a single service by ID.
 */
export function useService(id?: number | string) {
  const numericId = id ? Number(id) : undefined;
  return useQuery<Service>({
    queryKey: queryKeys.service(numericId ?? 0),
    queryFn: () => getService(numericId!),
    enabled: Boolean(numericId),
  });
}

/**
 * Mutation to create a new monitored service.
 */
export function useCreateService() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CreateServiceInput) => createService(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['services'] });
    },
  });
}

/**
 * Mutation to update an existing service.
 */
export function useUpdateService() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: UpdateServiceInput }) => updateService(id, data),
    onSuccess: (_data, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['services'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.service(id) });
    },
  });
}
