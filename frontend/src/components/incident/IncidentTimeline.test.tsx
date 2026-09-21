import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test-utils';
import { IncidentTimeline } from './IncidentTimeline';
import { IncidentEvent } from '../../types/incident';

const mockEvents: IncidentEvent[] = [
  {
    id: 1,
    incident_id: 101,
    event_type: 'INCIDENT_TRIGGERED',
    actor: null,
    metadata: { alert_id: 501 },
    created_at: '2026-09-21T10:00:00Z',
  },
  {
    id: 2,
    incident_id: 101,
    event_type: 'RESPONDER_ASSIGNED',
    actor: null,
    metadata: { target_user: 'alice@example.com' },
    created_at: '2026-09-21T10:00:01Z',
  },
  {
    id: 3,
    incident_id: 101,
    event_type: 'INCIDENT_ACKNOWLEDGED',
    actor: { id: 5, username: 'alice', email: 'alice@example.com', name: 'Alice Smith' },
    metadata: {},
    created_at: '2026-09-21T10:05:00Z',
  },
  {
    id: 4,
    incident_id: 101,
    event_type: 'INCIDENT_ESCALATED',
    actor: null,
    metadata: { level_number: 2, reason: 'Acknowledgement timeout expired' },
    created_at: '2026-09-21T10:15:00Z',
  },
  {
    id: 5,
    incident_id: 101,
    event_type: 'INCIDENT_RESOLVED',
    actor: { id: 5, username: 'alice', email: 'alice@example.com', name: 'Alice Smith' },
    metadata: { reason: 'Database failover completed successfully' },
    created_at: '2026-09-21T10:30:00Z',
  },
];

describe('IncidentTimeline Component', () => {
  it('renders all chronological events with human-readable labels and actors', () => {
    renderWithProviders(<IncidentTimeline events={mockEvents} />);

    expect(screen.getByText('Incident Triggered')).toBeInTheDocument();
    expect(screen.getByText('Responder Assigned')).toBeInTheDocument();
    expect(screen.getByText('Incident Acknowledged')).toBeInTheDocument();
    expect(screen.getByText('Incident Escalated')).toBeInTheDocument();
    expect(screen.getByText('Incident Resolved')).toBeInTheDocument();

    // Actor checks
    expect(screen.getAllByText('System / Automation').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('Alice Smith').length).toBeGreaterThanOrEqual(1);

    // Metadata chips
    expect(screen.getByText(/Escalation Level 2/i)).toBeInTheDocument();
    expect(screen.getByText(/Alert #501/i)).toBeInTheDocument();
  });

  it('renders clean fallback for unknown event types without crashing', () => {
    const unknownEvent: IncidentEvent = {
      id: 99,
      incident_id: 101,
      event_type: 'UNKNOWN_CUSTOM_TELEMETRY_LOG',
      actor: null,
      metadata: {},
      created_at: '2026-09-21T11:00:00Z',
    };

    renderWithProviders(<IncidentTimeline events={[unknownEvent]} />);

    expect(screen.getByText('Unknown Custom Telemetry Log')).toBeInTheDocument();
  });

  it('allows expanding raw metadata inspector', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IncidentTimeline events={mockEvents} />);

    const inspectButtons = screen.getAllByRole('button', { name: /show event payload/i });
    expect(inspectButtons.length).toBeGreaterThan(0);

    await user.click(inspectButtons[0]);

    expect(screen.getByText(/"alert_id": 501/)).toBeInTheDocument();
  });

  it('toggles sort order between oldest and newest first', async () => {
    const user = userEvent.setup();
    renderWithProviders(<IncidentTimeline events={mockEvents} />);

    const sortButton = screen.getByRole('button', { name: /oldest first/i });
    expect(sortButton).toBeInTheDocument();

    await user.click(sortButton);
    expect(screen.getByRole('button', { name: /newest first/i })).toBeInTheDocument();
  });

  it('renders empty state when no events exist', () => {
    renderWithProviders(<IncidentTimeline events={[]} />);

    expect(screen.getByText('No events recorded')).toBeInTheDocument();
  });
});
