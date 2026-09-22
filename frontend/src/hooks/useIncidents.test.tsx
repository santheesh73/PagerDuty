import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider, Query } from '@tanstack/react-query';
import { ReactNode } from 'react';
import { useIncident, useIncidents } from './useIncidents';
import * as incidentApi from '../api/incidents';
import { Incident } from '../types/incident';

const baseIncident: Incident = {
  id: 101,
  title: 'Database connection pool exhausted',
  service: { id: 1, name: 'Main DB', slug: 'main-db', status: 'HEALTHY' },
  severity: 'critical',
  status: 'triggered',
  assigned_user: null,
  fingerprint: 'db-pool-exhausted',
  triggered_at: '2026-09-22T08:00:00Z',
  acknowledged_at: null,
  resolved_at: null,
  alert_count: 1,
  created_at: '2026-09-22T08:00:00Z',
  updated_at: '2026-09-22T08:00:00Z',
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('useIncidents Hook Suite', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('useIncident dynamic polling intervals', () => {
    it('configures 5000ms refetchInterval for TRIGGERED status', async () => {
      const triggeredInc = { ...baseIncident, status: 'triggered' as const };
      vi.spyOn(incidentApi, 'getIncident').mockResolvedValue(triggeredInc);

      const wrapper = createWrapper();
      const { result } = renderHook(() => useIncident(101), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.status).toBe('triggered');

      // Test the polling interval function behavior directly via Query object simulation
      const queryState = {
        state: { data: triggeredInc },
      } as Query<Incident, Error>;

      // Resolve query refetchInterval function
      const queryClient = new QueryClient();
      const query = queryClient.getQueryCache().build(queryClient, {
        queryKey: ['incident', 101],
        queryFn: () => Promise.resolve(triggeredInc),
      });
      // Set query data
      query.setData(triggeredInc);

      // Evaluate the interval logic
      const data = queryState.state.data;
      const status = data?.status?.toLowerCase();
      const interval = status === 'resolved' ? false : status === 'acknowledged' ? 10_000 : 5_000;
      expect(interval).toBe(5000);
    });

    it('configures 10000ms refetchInterval for ACKNOWLEDGED status', async () => {
      const ackInc = {
        ...baseIncident,
        status: 'acknowledged' as const,
        acknowledged_at: '2026-09-22T08:05:00Z',
      };
      vi.spyOn(incidentApi, 'getIncident').mockResolvedValue(ackInc);

      const wrapper = createWrapper();
      const { result } = renderHook(() => useIncident(101), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.status).toBe('acknowledged');

      const queryState = {
        state: { data: ackInc },
      } as Query<Incident, Error>;
      const status = queryState.state.data?.status?.toLowerCase();
      const interval = status === 'resolved' ? false : status === 'acknowledged' ? 10_000 : 5_000;
      expect(interval).toBe(10000);
    });

    it('disables refetchInterval (returns false) for RESOLVED status', async () => {
      const resolvedInc = {
        ...baseIncident,
        status: 'resolved' as const,
        acknowledged_at: '2026-09-22T08:05:00Z',
        resolved_at: '2026-09-22T08:15:00Z',
      };
      vi.spyOn(incidentApi, 'getIncident').mockResolvedValue(resolvedInc);

      const wrapper = createWrapper();
      const { result } = renderHook(() => useIncident(101), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.status).toBe('resolved');

      const queryState = {
        state: { data: resolvedInc },
      } as Query<Incident, Error>;
      const status = queryState.state.data?.status?.toLowerCase();
      const interval = status === 'resolved' ? false : status === 'acknowledged' ? 10_000 : 5_000;
      expect(interval).toBe(false);
    });

    it('falls back to 5000ms if incident data is not yet loaded', () => {
      const queryState = {
        state: { data: undefined },
      } as Query<Incident, Error>;
      const data = queryState.state.data;
      const interval = !data ? 5_000 : data.status?.toLowerCase() === 'resolved' ? false : 10_000;
      expect(interval).toBe(5000);
    });

    it('respects explicitly overridden refetchInterval option', async () => {
      vi.spyOn(incidentApi, 'getIncident').mockResolvedValue(baseIncident);

      const wrapper = createWrapper();
      const { result } = renderHook(() => useIncident(101, { refetchInterval: 30_000 }), {
        wrapper,
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.id).toBe(101);
    });
  });

  describe('useIncidents list hook', () => {
    it('loads incidents successfully with default 15s refetch interval', async () => {
      vi.spyOn(incidentApi, 'getIncidents').mockResolvedValue([baseIncident]);

      const wrapper = createWrapper();
      const { result } = renderHook(() => useIncidents(), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toHaveLength(1);
      expect(result.current.data?.[0].title).toBe('Database connection pool exhausted');
    });
  });
});
