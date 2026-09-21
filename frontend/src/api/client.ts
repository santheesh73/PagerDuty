import { ApiError, ApiErrorData } from '../types/api';

export { ApiError };
export type { ApiErrorData };

export const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000/api';

/**
 * Extracts Django CSRF token from document.cookie if available.
 */
export function getCsrfToken(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Normalizes DRF error responses into a structured ApiError.
 */
export function parseDrfError(status: number, data: unknown, fallbackMessage: string): ApiError {
  let message = fallbackMessage;

  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if (typeof obj.detail === 'string') {
      message = obj.detail;
    } else if (Array.isArray(obj.non_field_errors) && obj.non_field_errors.length > 0) {
      message = String(obj.non_field_errors[0]);
    } else {
      // Find the first field error if available
      const firstEntry = Object.entries(obj).find(
        ([key, val]) => key !== 'detail' && (Array.isArray(val) || typeof val === 'string')
      );
      if (firstEntry) {
        const [field, val] = firstEntry;
        const fieldMsg = Array.isArray(val) ? val[0] : val;
        message = `${field}: ${fieldMsg}`;
      }
    }
  }

  return new ApiError(message, status, data as ApiErrorData);
}

export interface RequestOptions extends RequestInit {
  params?: Record<string, string | number | boolean | undefined | null>;
}

/**
 * Base HTTP client function.
 */
export async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { params, ...fetchOptions } = options;

  let urlPath = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;

  if (params) {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value !== undefined && value !== null) {
        searchParams.append(key, String(value));
      }
    }
    const queryString = searchParams.toString();
    if (queryString) {
      urlPath += (urlPath.includes('?') ? '&' : '?') + queryString;
    }
  }

  const url = `${API_BASE_URL}${urlPath}`;

  const defaultHeaders: Record<string, string> = {
    Accept: 'application/json',
  };

  if (fetchOptions.body && !(fetchOptions.body instanceof FormData)) {
    defaultHeaders['Content-Type'] = 'application/json';
  }

  const method = (fetchOptions.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      defaultHeaders['X-CSRFToken'] = csrfToken;
    }
  }

  let response: Response;
  try {
    response = await fetch(url, {
      credentials: 'include',
      ...fetchOptions,
      headers: {
        ...defaultHeaders,
        ...fetchOptions.headers,
      },
    });
  } catch (error) {
    const msg = error instanceof Error ? error.message : 'Network error or server unreachable';
    throw new ApiError(msg, 0);
  }

  if (!response.ok) {
    let errorData: unknown;
    try {
      errorData = await response.json();
    } catch {
      errorData = await response.text();
    }
    throw parseDrfError(
      response.status,
      errorData,
      `Request to ${endpoint} failed with status ${response.status}`
    );
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  get: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(endpoint: string, body?: unknown, options?: RequestOptions) =>
    request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(endpoint: string, options?: RequestOptions) =>
    request<T>(endpoint, { ...options, method: 'DELETE' }),
};
