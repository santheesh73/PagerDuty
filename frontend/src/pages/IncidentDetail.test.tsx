import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { IncidentDetail } from './IncidentDetail';
import * as incidentApi from '../api/incidents';
import * as notificationApi from '../api/notifications';
import { Incident, IncidentEvent } from '../types/incident';
import { ApiError } from '../api/client';

import { Routes, Route } from 'react-router-dom';

const mockIncident: Incident = {
  id: 42,
  title: 'Redis Cluster Split Brain',
  service: { id: 2, name: 'Caching Tier', slug: 'caching-tier', status: 'HEALTHY' },
  severity: 'high',
  status: 'triggered',
  assigned_user: { id: 7, username: 'devops', email: 'devops@example.com', name: 'DevOps OnCall' },
  fingerprint: 'fp-split-brain-42',
  triggered_at: '2026-09-21T09:00:00Z',
  acknowledged_at: null,
  resolved_at: null,
  alert_count: 2,
  created_at: '2026-09-21T09:00:00Z',
  updated_at: '2026-09-21T09:00:00Z',
};

const mockEvents: IncidentEvent[] = [
  {
    id: 1,
    incident_id: 42,
    event_type: 'INCIDENT_TRIGGERED',
    actor: null,
    metadata: {},
    created_at: '2026-09-21T09:00:00Z',
  },
];

describe('IncidentDetail Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(notificationApi, 'getNotifications').mockResolvedValue([]);
  });

  it('renders incident attributes, responder card, actions, and timeline', async () => {
    vi.spyOn(incidentApi, 'getIncident').mockResolvedValue(mockIncident);
    vi.spyOn(incidentApi, 'getIncidentEvents').mockResolvedValue(mockEvents);

    renderWithProviders(
      <Routes>
        <Route path="/incidents/:incidentId" element={<IncidentDetail />} />
      </Routes>,
      { route: '/incidents/42' }
    );

    expect(await screen.findByText('Redis Cluster Split Brain')).toBeInTheDocument();
    expect(screen.getByText('INC-0042')).toBeInTheDocument();
    expect(screen.getByText('Back to Incidents')).toBeInTheDocument();
    expect(screen.getAllByText('Caching Tier').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('DevOps OnCall')).toBeInTheDocument();
    expect(screen.getByText('fp-split-brain-42')).toBeInTheDocument();
    expect(screen.getByText(/2 alerts deduplicated/i)).toBeInTheDocument();
    expect(screen.getByText('Incident Timeline')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /acknowledge/i })).toBeInTheDocument();
  });

  it('renders 404 / not found error state when incident cannot be fetched', async () => {
    vi.spyOn(incidentApi, 'getIncident').mockRejectedValue(
      new ApiError('Not found.', 404)
    );
    vi.spyOn(incidentApi, 'getIncidentEvents').mockResolvedValue([]);

    renderWithProviders(
      <Routes>
        <Route path="/incidents/:incidentId" element={<IncidentDetail />} />
      </Routes>,
      { route: '/incidents/999' }
    );

    expect(await screen.findByText('Incident Not Found')).toBeInTheDocument();
    expect(screen.getByText('Back to Incidents')).toBeInTheDocument();
  });
});
