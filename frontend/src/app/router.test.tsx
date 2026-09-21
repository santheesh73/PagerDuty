import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { AppRoutes } from './router';

describe('SPA Router', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: 'ok', dependencies: { database: 'ok', redis: 'ok' } }),
    } as Response);
  });

  it('renders Dashboard placeholder at root path /', () => {
    renderWithProviders(<AppRoutes />, { route: '/' });

    expect(screen.getByRole('heading', { level: 1, name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getAllByText(/Phase 7/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole('heading', { level: 3, name: 'Operational Dashboard' })).toBeInTheDocument();
  });

  it('renders Incidents placeholder at /incidents', () => {
    renderWithProviders(<AppRoutes />, { route: '/incidents' });

    expect(screen.getByRole('heading', { level: 1, name: 'Incidents' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Incident Workbench' })).toBeInTheDocument();
  });

  it('renders IncidentDetail placeholder with route param at /incidents/:incidentId', () => {
    renderWithProviders(<AppRoutes />, { route: '/incidents/42' });

    expect(screen.getByRole('heading', { level: 1, name: 'Incident #42' })).toBeInTheDocument();
    expect(screen.getByText(/Back to Incidents/i)).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Incident Timeline & Actions' })).toBeInTheDocument();
  });

  it('renders Services placeholder at /services', () => {
    renderWithProviders(<AppRoutes />, { route: '/services' });

    expect(screen.getByRole('heading', { level: 1, name: 'Services' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3, name: 'Service Catalog' })).toBeInTheDocument();
    expect(screen.getAllByText(/Phase 8/i).length).toBeGreaterThanOrEqual(1);
  });

  it('renders On-call Schedules placeholder at /on-call', () => {
    renderWithProviders(<AppRoutes />, { route: '/on-call' });

    expect(screen.getByRole('heading', { level: 1, name: 'On-call Schedules' })).toBeInTheDocument();
    expect(screen.getByText(/Schedule Management/i)).toBeInTheDocument();
  });

  it('renders Escalation Policies placeholder at /escalation-policies', () => {
    renderWithProviders(<AppRoutes />, { route: '/escalation-policies' });

    expect(screen.getByRole('heading', { level: 1, name: 'Escalation Policies' })).toBeInTheDocument();
    expect(screen.getByText(/Escalation Policy Editor/i)).toBeInTheDocument();
  });

  it('renders Analytics placeholder at /analytics', () => {
    renderWithProviders(<AppRoutes />, { route: '/analytics' });

    expect(screen.getByRole('heading', { level: 1, name: 'Analytics' })).toBeInTheDocument();
    expect(screen.getByText(/Incident Analytics & Reporting/i)).toBeInTheDocument();
  });

  it('renders NotFound component for unknown routes', () => {
    renderWithProviders(<AppRoutes />, { route: '/some-non-existent-route' });

    expect(screen.getByText(/404 — Page Not Found/i)).toBeInTheDocument();
    expect(screen.getByText(/Return to Dashboard/i)).toBeInTheDocument();
  });
});
