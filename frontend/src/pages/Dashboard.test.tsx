import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { Dashboard } from './Dashboard';
import * as incidentApi from '../api/incidents';
import { Incident } from '../types/incident';

const mockIncidents: Incident[] = [
  {
    id: 1,
    title: 'API Gateway 502 Outage',
    service: { id: 1, name: 'API Gateway', slug: 'api-gateway', status: 'HEALTHY' },
    severity: 'critical',
    status: 'triggered',
    assigned_user: null,
    fingerprint: 'fp-1',
    triggered_at: '2026-09-21T10:00:00Z',
    acknowledged_at: null,
    resolved_at: null,
    alert_count: 5,
    created_at: '2026-09-21T10:00:00Z',
    updated_at: '2026-09-21T10:00:00Z',
  },
  {
    id: 2,
    title: 'High CPU on worker nodes',
    service: { id: 2, name: 'Worker Service', slug: 'worker-service', status: 'HEALTHY' },
    severity: 'high',
    status: 'acknowledged',
    assigned_user: { id: 3, username: 'bob', email: 'bob@example.com', name: 'Bob Roberts' },
    fingerprint: 'fp-2',
    triggered_at: '2026-09-21T09:30:00Z',
    acknowledged_at: '2026-09-21T09:35:00Z',
    resolved_at: null,
    alert_count: 2,
    created_at: '2026-09-21T09:30:00Z',
    updated_at: '2026-09-21T09:35:00Z',
  },
  {
    id: 3,
    title: 'DNS latency spike',
    service: { id: 3, name: 'Edge DNS', slug: 'edge-dns', status: 'HEALTHY' },
    severity: 'low',
    status: 'resolved',
    assigned_user: { id: 4, username: 'carol', email: 'carol@example.com', name: 'Carol Danvers' },
    fingerprint: 'fp-3',
    triggered_at: '2026-09-21T08:00:00Z',
    acknowledged_at: '2026-09-21T08:05:00Z',
    resolved_at: '2026-09-21T08:20:00Z',
    alert_count: 1,
    created_at: '2026-09-21T08:00:00Z',
    updated_at: '2026-09-21T08:20:00Z',
  },
];

describe('Dashboard Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders operational KPIs derived from backend incident dataset', async () => {
    vi.spyOn(incidentApi, 'getIncidents').mockResolvedValue(mockIncidents);

    renderWithProviders(<Dashboard />);

    expect(
      screen.getByRole('heading', { level: 1, name: 'Operations Dashboard' })
    ).toBeInTheDocument();

    // Active Incidents count: 2 (triggered + acknowledged)
    const countTwos = await screen.findAllByText('2');
    expect(countTwos.length).toBeGreaterThanOrEqual(1);

    // Critical count: 1 (incident 1)
    // Triggered count: 1 (incident 1)
    // Acknowledged count: 1 (incident 2)
    const countOnes = await screen.findAllByText('1');
    expect(countOnes.length).toBeGreaterThanOrEqual(1);

    // Queue heading
    expect(screen.getByText('Needs Immediate Attention')).toBeInTheDocument();
    expect(screen.getByText('API Gateway 502 Outage')).toBeInTheDocument();

    // Recently updated / resolved
    expect(screen.getByText('Recently Updated or Resolved')).toBeInTheDocument();
    expect(screen.getByText('DNS latency spike')).toBeInTheDocument();
  });

  it('displays empty state message when no active incidents need attention', async () => {
    vi.spyOn(incidentApi, 'getIncidents').mockResolvedValue([mockIncidents[2]]); // only resolved

    renderWithProviders(<Dashboard />);

    expect(
      await screen.findByText('All clear! No incidents need immediate attention.')
    ).toBeInTheDocument();
  });
});
