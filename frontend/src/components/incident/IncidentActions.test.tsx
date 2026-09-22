import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '../../test-utils';
import { IncidentActions } from './IncidentActions';
import { Incident } from '../../types/incident';
import * as incidentApi from '../../api/incidents';
import { ApiError } from '../../api/client';

const mockTriggeredIncident: Incident = {
  id: 101,
  title: 'Database connection pool exhausted',
  service: { id: 1, name: 'Billing Service', slug: 'billing-service', status: 'HEALTHY' },
  severity: 'critical',
  status: 'triggered',
  assigned_user: { id: 5, username: 'alice', email: 'alice@example.com', name: 'Alice Smith' },
  fingerprint: 'fp-101',
  triggered_at: '2026-09-21T10:00:00Z',
  acknowledged_at: null,
  resolved_at: null,
  alert_count: 3,
  created_at: '2026-09-21T10:00:00Z',
  updated_at: '2026-09-21T10:00:00Z',
};

const mockAcknowledgedIncident: Incident = {
  ...mockTriggeredIncident,
  status: 'acknowledged',
  acknowledged_at: '2026-09-21T10:05:00Z',
};

const mockResolvedIncident: Incident = {
  ...mockTriggeredIncident,
  status: 'resolved',
  acknowledged_at: '2026-09-21T10:05:00Z',
  resolved_at: '2026-09-21T10:30:00Z',
};

describe('IncidentActions Component', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders active Acknowledge and Resolve buttons for TRIGGERED incident', () => {
    renderWithProviders(<IncidentActions incident={mockTriggeredIncident} />);

    const ackButton = screen.getByRole('button', { name: /acknowledge/i });
    const resolveButton = screen.getByRole('button', { name: /resolve/i });

    expect(ackButton).toBeEnabled();
    expect(resolveButton).toBeEnabled();
    expect(screen.queryByRole('button', { name: /reopen/i })).not.toBeInTheDocument();
  });

  it('triggers acknowledge mutation when Acknowledge button is clicked', async () => {
    const user = userEvent.setup();
    const ackSpy = vi.spyOn(incidentApi, 'acknowledgeIncident').mockResolvedValue({
      ...mockTriggeredIncident,
      status: 'acknowledged',
      acknowledged_at: '2026-09-21T10:05:00Z',
    });

    renderWithProviders(<IncidentActions incident={mockTriggeredIncident} />);

    const ackButton = screen.getByRole('button', { name: /acknowledge/i });
    await user.click(ackButton);

    expect(ackSpy).toHaveBeenCalledWith(101);
  });

  it('disables Acknowledge button and enables Resolve for ACKNOWLEDGED incident', () => {
    renderWithProviders(<IncidentActions incident={mockAcknowledgedIncident} />);

    const ackButton = screen.getByRole('button', { name: /acknowledged/i });
    const resolveButton = screen.getByRole('button', { name: /resolve/i });

    expect(ackButton).toBeDisabled();
    expect(resolveButton).toBeEnabled();
    expect(screen.queryByRole('button', { name: /reopen/i })).not.toBeInTheDocument();
  });

  it('triggers resolve mutation when Resolve button is clicked', async () => {
    const user = userEvent.setup();
    const resolveSpy = vi.spyOn(incidentApi, 'resolveIncident').mockResolvedValue({
      ...mockAcknowledgedIncident,
      status: 'resolved',
      resolved_at: '2026-09-21T10:30:00Z',
    });

    renderWithProviders(<IncidentActions incident={mockAcknowledgedIncident} />);

    const resolveButton = screen.getByRole('button', { name: /resolve/i });
    await user.click(resolveButton);

    expect(resolveSpy).toHaveBeenCalledWith(101);
  });

  it('disables Resolve and renders active Reopen button for RESOLVED incident', () => {
    renderWithProviders(<IncidentActions incident={mockResolvedIncident} />);

    const ackButton = screen.getByRole('button', { name: /acknowledge/i });
    const resolveButton = screen.getByRole('button', { name: /resolved/i });
    const reopenButton = screen.getByRole('button', { name: /reopen incident/i });

    expect(ackButton).toBeDisabled();
    expect(resolveButton).toBeDisabled();
    expect(reopenButton).toBeEnabled();
  });

  it('triggers reopen mutation when Reopen button is clicked', async () => {
    const user = userEvent.setup();
    const reopenSpy = vi.spyOn(incidentApi, 'reopenIncident').mockResolvedValue({
      ...mockResolvedIncident,
      status: 'triggered',
      resolved_at: null,
    });

    renderWithProviders(<IncidentActions incident={mockResolvedIncident} />);

    const reopenButton = screen.getByRole('button', { name: /reopen incident/i });
    await user.click(reopenButton);

    const confirmButton = screen.getByRole('button', { name: /confirm reopen/i });
    await user.click(confirmButton);

    expect(reopenSpy).toHaveBeenCalledWith(101);
  });

  it('displays conflict banner and recovers gracefully when receiving 409 Conflict', async () => {
    const user = userEvent.setup();
    vi.spyOn(incidentApi, 'acknowledgeIncident').mockRejectedValue(
      new ApiError('Incident is already resolved and cannot be acknowledged.', 409)
    );

    renderWithProviders(<IncidentActions incident={mockTriggeredIncident} />);

    const ackButton = screen.getByRole('button', { name: /acknowledge/i });
    await user.click(ackButton);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
      expect(screen.getByText(/State Conflict Detected/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Incident is already resolved and cannot be acknowledged/i)
      ).toBeInTheDocument();
    });
  });
});
