import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getHealth } from './health';

describe('Health API', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('fetches health status successfully', async () => {
    const mockData = { status: 'ok', dependencies: { database: 'ok' } };
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    } as unknown as Response);

    const result = await getHealth();
    expect(result).toEqual(mockData);
    expect(global.fetch).toHaveBeenCalledWith(
      expect.stringContaining('/health/'),
      expect.objectContaining({
        headers: expect.objectContaining({
          Accept: 'application/json',
        }),
      })
    );
  });

  it('throws ApiError when backend returns non-200 status', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => 'Service Unavailable',
    } as unknown as Response);

    await expect(getHealth()).rejects.toThrow(/status 503/i);
  });
});
