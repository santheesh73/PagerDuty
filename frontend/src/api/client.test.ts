import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { apiClient, ApiError, API_BASE_URL } from './client';

describe('API Client', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.resetAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
    document.cookie = '';
  });

  it('uses environment-driven API base URL and performs successful GET request', async () => {
    expect(API_BASE_URL).toBeDefined();

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 1, name: 'Payment API' }),
    } as Response);

    const result = await apiClient.get<{ id: number; name: string }>('/services/1/');

    expect(global.fetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/services/1/`,
      expect.objectContaining({
        method: 'GET',
        credentials: 'include',
        headers: expect.objectContaining({
          Accept: 'application/json',
        }),
      })
    );
    expect(result).toEqual({ id: 1, name: 'Payment API' });
  });

  it('correctly appends query params on GET request', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => [],
    } as Response);

    await apiClient.get('/incidents/', {
      params: { status: 'triggered', active: true, page: 2 },
    });

    expect(global.fetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/incidents/?status=triggered&active=true&page=2`,
      expect.anything()
    );
  });

  it('serializes JSON body on POST and attaches CSRF token from cookies', async () => {
    document.cookie = 'csrftoken=test-csrf-token-123; path=/';

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: 42, title: 'New Alert' }),
    } as Response);

    const payload = { message: 'CPU Spike', service_id: 1 };
    const result = await apiClient.post<{ id: number; title: string }>('/alerts/', payload);

    expect(global.fetch).toHaveBeenCalledWith(
      `${API_BASE_URL}/alerts/`,
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify(payload),
        headers: expect.objectContaining({
          'Content-Type': 'application/json',
          Accept: 'application/json',
          'X-CSRFToken': 'test-csrf-token-123',
        }),
      })
    );
    expect(result).toEqual({ id: 42, title: 'New Alert' });
  });

  it('normalizes DRF detail error response into structured ApiError', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Service does not exist.' }),
    } as Response);

    await expect(apiClient.get('/services/999/')).rejects.toThrow(ApiError);

    try {
      await apiClient.get('/services/999/');
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(404);
      expect(apiErr.message).toBe('Service does not exist.');
    }
  });

  it('normalizes DRF field error responses and populates fieldErrors dictionary', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({
        service_id: ['Service does not exist.'],
        severity: ['Invalid choice.'],
      }),
    } as Response);

    try {
      await apiClient.post('/alerts/', {});
      expect.fail('Should have thrown ApiError');
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(400);
      expect(apiErr.fieldErrors).toBeDefined();
      expect(apiErr.fieldErrors?.service_id).toEqual(['Service does not exist.']);
      expect(apiErr.fieldErrors?.severity).toEqual(['Invalid choice.']);
      expect(apiErr.message).toContain('Service does not exist.');
    }
  });

  it('normalizes network exceptions into status 0 ApiError', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Failed to fetch (connection refused)'));

    try {
      await apiClient.get('/health/');
      expect.fail('Should have thrown ApiError');
    } catch (err) {
      const apiErr = err as ApiError;
      expect(apiErr.status).toBe(0);
      expect(apiErr.message).toBe('Failed to fetch (connection refused)');
    }
  });
});
