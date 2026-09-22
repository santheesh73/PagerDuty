import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../test-utils';
import { Analytics } from './Analytics';
import * as analyticsApi from '../api/analytics';
import {
  AnalyticsSummary,
  IncidentTrendPoint,
  ServiceIncidentCount,
  SeverityCount,
} from '../types/analytics';

const mockSummary: AnalyticsSummary = {
  range_days: 30,
  incident_count: 120,
  active_incidents: 4,
  critical_incidents: 2,
  mtta_seconds: 135, // 2m 15s
  mttr_seconds: 2100, // 35m
};

const mockServiceBreakdown: ServiceIncidentCount[] = [
  { service_id: 1, service_name: 'Auth Gateway', count: 80 },
  { service_id: 2, service_name: 'Billing API', count: 40 },
];

const mockSeverityDist: SeverityCount[] = [
  { severity: 'CRITICAL', count: 10 },
  { severity: 'HIGH', count: 30 },
  { severity: 'MEDIUM', count: 50 },
  { severity: 'LOW', count: 30 },
];

const mockTrend: IncidentTrendPoint[] = [
  { date: '2026-09-20', count: 5 },
  { date: '2026-09-21', count: 8 },
];

describe('Analytics Page', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(analyticsApi, 'getAnalyticsSummary').mockResolvedValue(mockSummary);
    vi.spyOn(analyticsApi, 'getIncidentsByService').mockResolvedValue(mockServiceBreakdown);
    vi.spyOn(analyticsApi, 'getSeverityDistribution').mockResolvedValue(mockSeverityDist);
    vi.spyOn(analyticsApi, 'getIncidentTrend').mockResolvedValue(mockTrend);
  });

  it('renders authoritative KPI cards with humanized MTTA and MTTR', async () => {
    renderWithProviders(<Analytics />);

    expect(screen.getByRole('heading', { level: 1, name: 'Analytics' })).toBeInTheDocument();

    // Authoritative KPIs
    expect(await screen.findByText('120')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('2m 15s')).toBeInTheDocument(); // MTTA: 135s
    expect(screen.getByText('35m')).toBeInTheDocument(); // MTTR: 2100s
  });

  it('renders service breakdown, severity distribution, and daily trend', async () => {
    renderWithProviders(<Analytics />);

    expect(await screen.findByText('Auth Gateway')).toBeInTheDocument();
    expect(screen.getByText('80 incidents')).toBeInTheDocument();
    expect(screen.getByText('(67%)')).toBeInTheDocument();

    expect(screen.getByText('Billing API')).toBeInTheDocument();
    expect(screen.getByText('40 incidents')).toBeInTheDocument();

    // Severity distribution
    expect(screen.getByText('Severity Distribution')).toBeInTheDocument();
    expect(screen.getByTestId('severity-stat-critical')).toBeInTheDocument();

    // Trend chart
    expect(screen.getByText('Daily Incident Trend')).toBeInTheDocument();
    expect(screen.getByTestId('trend-bar-2026-09-20')).toBeInTheDocument();
    expect(screen.getByTestId('trend-bar-2026-09-21')).toBeInTheDocument();
  });

  it('handles null MTTA/MTTR gracefully as N/A', async () => {
    vi.spyOn(analyticsApi, 'getAnalyticsSummary').mockResolvedValue({
      ...mockSummary,
      mtta_seconds: null,
      mttr_seconds: null,
    });

    renderWithProviders(<Analytics />);

    const naElements = await screen.findAllByText('N/A');
    expect(naElements.length).toBeGreaterThanOrEqual(2);
  });

  it('refetches with new range when 7 Days button is clicked', async () => {
    renderWithProviders(<Analytics />);
    await screen.findByText('120');

    fireEvent.click(screen.getByRole('button', { name: '7 Days' }));

    await waitFor(() => {
      expect(analyticsApi.getAnalyticsSummary).toHaveBeenCalledWith('7d');
      expect(analyticsApi.getIncidentsByService).toHaveBeenCalledWith('7d');
      expect(analyticsApi.getSeverityDistribution).toHaveBeenCalledWith('7d');
      expect(analyticsApi.getIncidentTrend).toHaveBeenCalledWith('7d');
    });
  });
});
