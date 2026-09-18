import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import App from './App';

describe('App Component', () => {
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

  it('renders the application shell and header', () => {
    // Mock fetch that never resolves to test loading
    global.fetch = vi.fn().mockImplementation(() => new Promise(() => {}));

    render(<App client={queryClient} />);

    expect(screen.getByText('Incident Management Platform')).toBeInTheDocument();
    expect(screen.getByText(/Phase: 0 — Skeleton/i)).toBeInTheDocument();
    expect(screen.getByText('System Connectivity')).toBeInTheDocument();
    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });

  it('displays Connected when backend returns healthy status', async () => {
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

    expect(screen.getByText('database')).toBeInTheDocument();
    expect(screen.getByText('redis')).toBeInTheDocument();
  });

  it('displays Unavailable when backend health check fails', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Network connection failed'));

    render(<App client={queryClient} />);

    await waitFor(() => {
      expect(screen.getByText('Unavailable')).toBeInTheDocument();
    });

    expect(screen.getByText(/Network connection failed/i)).toBeInTheDocument();
  });
});
