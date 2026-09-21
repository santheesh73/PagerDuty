import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { renderWithProviders } from '../../test-utils';
import { TopBar } from './TopBar';

describe('TopBar Component & Health Integration', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('displays Connected badge when backend returns healthy status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        status: 'ok',
        dependencies: { database: 'ok', redis: 'ok' },
      }),
    } as unknown as Response);

    renderWithProviders(<TopBar />);

    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument();
    });
    expect(screen.getByText(/Operations Center/i)).toBeInTheDocument();
  });

  it('displays Unavailable badge when health query fails without breaking UI', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Connection refused'));

    renderWithProviders(<TopBar />);

    await waitFor(() => {
      expect(screen.getByText('Unavailable')).toBeInTheDocument();
    });
    expect(screen.getByText(/Operations Center/i)).toBeInTheDocument();
  });
});
