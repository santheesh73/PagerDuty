import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import App from './App';

describe('App Root Component', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.resetAllMocks();
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
          gcTime: 0,
        },
      },
    });
  });

  it('renders the complete application shell, sidebar, and dashboard', () => {
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    render(<App client={queryClient} />);

    // Brand and platform title
    expect(screen.getByText('IncidentPlatform')).toBeInTheDocument();
    expect(screen.getByText('Core Workbench')).toBeInTheDocument();

    // Navigation links in Sidebar
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Incidents' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Services' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'On-call' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Escalation Policies' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Analytics' })).toBeInTheDocument();

    // Default route content (Dashboard)
    expect(screen.getByRole('heading', { level: 1, name: 'Operations Dashboard' })).toBeInTheDocument();
    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });

  it('displays Connected badge when backend returns healthy status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'ok',
        dependencies: {
          database: 'ok',
          redis: 'ok',
        },
      }),
    } as unknown as Response);

    render(<App client={queryClient} />);

    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument();
    });
  });

  it('displays Unavailable badge when backend health check fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network connection failed'));

    render(<App client={queryClient} />);

    await waitFor(() => {
      expect(screen.getByText('Unavailable')).toBeInTheDocument();
    });
  });
});
