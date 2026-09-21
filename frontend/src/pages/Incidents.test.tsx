import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { Incidents } from './Incidents';
import * as incidentApi from '../api/incidents';
import * as serviceApi from '../api/services';
import { Incident } from '../types/incident';

const mockIncidents: Incident[] = [
  {
    id: 101,
    title: 'PostgreSQL connection timeout',
    service: { id: 1, name: 'Database Primary', slug: 'db-primary', status: 'HEALTHY' },
    severity: 'critical',
    status: 'triggered',
    assigned_user: null,
    fingerprint: 'fp-101',
    triggered_at: '2026-09-21T10:00:00Z',
    acknowledged_at: null,
    resolved_at: null,
    alert_count: 4,
    created_at: '2026-09-21T10:00:00Z',
    updated_at: '2026-09-21T10:00:00Z',
  },
];

describe('Incidents Workbench Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(serviceApi, 'getServices').mockResolvedValue([
      {
        id: 1,
        name: 'Database Primary',
        slug: 'db-primary',
        status: 'HEALTHY',
        is_active: true,
        team: { id: 1, name: 'Core Team', slug: 'core-team', is_active: true },
        description: '',
        created_at: '',
        updated_at: '',
      },
    ]);
  });

  it('renders incidents table and total/active badges', async () => {
    vi.spyOn(incidentApi, 'getIncidents').mockResolvedValue(mockIncidents);

    renderWithProviders(<Incidents />);

    expect(screen.getByRole('heading', { level: 1, name: 'Incident Workbench' })).toBeInTheDocument();
    expect(await screen.findByText('PostgreSQL connection timeout')).toBeInTheDocument();
    expect(screen.getByText('Total:')).toBeInTheDocument();
    expect(screen.getByText('Active:')).toBeInTheDocument();
    expect(screen.getByText('Filters:')).toBeInTheDocument();
  });

  it('renders empty message when no incidents match', async () => {
    vi.spyOn(incidentApi, 'getIncidents').mockResolvedValue([]);

    renderWithProviders(<Incidents />);

    expect(await screen.findByText('No incidents found')).toBeInTheDocument();
  });
});
