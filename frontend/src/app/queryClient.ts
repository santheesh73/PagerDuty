import { QueryClient } from '@tanstack/react-query';

export const createDefaultQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        retry: 1,
        refetchOnWindowFocus: true,
      },
      mutations: {
        retry: false,
      },
    },
  });

export const createTestQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        gcTime: 0,
        refetchOnWindowFocus: false,
      },
      mutations: {
        retry: false,
      },
    },
  });

/**
 * Predictable, structured query keys for TanStack Query caching.
 */
export const queryKeys = {
  health: ['health'] as const,

  incidents: (filters?: Record<string, unknown>) => ['incidents', filters] as const,
  incident: (id: number | string) => ['incident', id] as const,
  incidentEvents: (id: number | string) => ['incident', id, 'events'] as const,

  services: (filters?: Record<string, unknown>) => ['services', filters] as const,
  service: (id: number | string) => ['service', id] as const,

  schedules: (filters?: Record<string, unknown>) => ['schedules', filters] as const,
  schedule: (id: number | string) => ['schedule', id] as const,
  scheduleRotations: (scheduleId: number | string) => ['schedule', scheduleId, 'rotations'] as const,
  currentOnCall: (scheduleId: number | string, timestamp?: string) =>
    ['schedule', scheduleId, 'on-call', timestamp] as const,

  escalationPolicies: (filters?: Record<string, unknown>) => ['escalation-policies', filters] as const,
  escalationPolicy: (id: number | string) => ['escalation-policy', id] as const,
  escalationLevels: (policyId?: number | string) => ['escalation-levels', policyId] as const,

  notifications: (filters?: Record<string, unknown>) => ['notifications', filters] as const,
  notification: (id: number | string) => ['notification', id] as const,
};
