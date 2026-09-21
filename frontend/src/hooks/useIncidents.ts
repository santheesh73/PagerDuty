import { useQuery, useMutation, useQueryClient, Query } from '@tanstack/react-query';
import { Incident, IncidentEvent } from '../types/incident';
import { Notification } from '../types/notification';
import {
  IncidentFilters,
  getIncidents,
  getIncident,
  getIncidentEvents,
  acknowledgeIncident,
  resolveIncident,
  reopenIncident,
} from '../api/incidents';
import { getNotifications } from '../api/notifications';
import { queryKeys } from '../app/queryClient';

export interface UseIncidentsOptions {
  refetchInterval?: number | false | ((query: Query<Incident[], Error>) => number | false);
  enabled?: boolean;
}

/**
 * Hook to fetch filtered operational incidents with background polling.
 */
export function useIncidents(filters?: IncidentFilters, options?: UseIncidentsOptions) {
  return useQuery({
    queryKey: queryKeys.incidents(filters as Record<string, unknown>),
    queryFn: () => getIncidents(filters),
    refetchInterval: options?.refetchInterval ?? 15_000,
    enabled: options?.enabled ?? true,
  });
}

export interface UseIncidentOptions {
  refetchInterval?: number | false | ((query: Query<Incident, Error>) => number | false);
  enabled?: boolean;
}

/**
 * Hook to fetch single incident details with status-aware dynamic polling:
 * - TRIGGERED: 5000ms
 * - ACKNOWLEDGED: 10000ms
 * - RESOLVED: disabled (false)
 */
export function useIncident(id: number | string | undefined, options?: UseIncidentOptions) {
  const numericId = id ? Number(id) : undefined;

  return useQuery({
    queryKey: queryKeys.incident(numericId ?? 0),
    queryFn: () => getIncident(numericId!),
    enabled: Boolean(numericId) && (options?.enabled ?? true),
    refetchInterval:
      options?.refetchInterval !== undefined
        ? options.refetchInterval
        : (query: Query<Incident, Error>) => {
            const data = query.state.data;
            if (!data) return 5_000;
            const status = data.status?.toLowerCase();
            if (status === 'resolved') return false;
            if (status === 'acknowledged') return 10_000;
            return 5_000;
          },
  });
}

export interface UseIncidentEventsOptions {
  refetchInterval?: number | false | ((query: Query<IncidentEvent[], Error>) => number | false);
  enabled?: boolean;
}

/**
 * Hook to fetch chronological incident audit timeline.
 */
export function useIncidentEvents(
  id: number | string | undefined,
  options?: UseIncidentEventsOptions
) {
  const numericId = id ? Number(id) : undefined;

  return useQuery({
    queryKey: queryKeys.incidentEvents(numericId ?? 0),
    queryFn: () => getIncidentEvents(numericId!),
    enabled: Boolean(numericId) && (options?.enabled ?? true),
    refetchInterval: options?.refetchInterval ?? 10_000,
  });
}

/**
 * Hook to fetch delivery notifications associated with an incident.
 */
export function useIncidentNotifications(
  incidentId: number | string | undefined,
  options?: { enabled?: boolean }
) {
  const numericId = incidentId ? Number(incidentId) : undefined;

  return useQuery<Notification[]>({
    queryKey: queryKeys.notifications({ incident: numericId }),
    queryFn: () => getNotifications({ incident: numericId }),
    enabled: Boolean(numericId) && (options?.enabled ?? true),
  });
}

/**
 * Authoritative mutation to acknowledge an incident.
 * Invalidates incident detail, incident list, timeline events, and notifications.
 */
export function useAcknowledgeIncident() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => acknowledgeIncident(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.incident(id) });
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.incidentEvents(id) });
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

/**
 * Authoritative mutation to resolve an incident.
 * Invalidates incident detail, incident list, timeline events, and notifications.
 */
export function useResolveIncident() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => resolveIncident(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.incident(id) });
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.incidentEvents(id) });
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}

/**
 * Authoritative mutation to reopen an incident.
 * Invalidates incident detail, incident list, timeline events, and notifications.
 */
export function useReopenIncident() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => reopenIncident(id),
    onSuccess: (_data, id) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.incident(id) });
      queryClient.invalidateQueries({ queryKey: ['incidents'] });
      queryClient.invalidateQueries({ queryKey: queryKeys.incidentEvents(id) });
      queryClient.invalidateQueries({ queryKey: ['notifications'] });
    },
  });
}
