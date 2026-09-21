/**
 * Standard API error model normalizing DRF responses.
 */
export interface ApiErrorData {
  detail?: string;
  non_field_errors?: string[];
  [field: string]: unknown;
}

export class ApiError extends Error {
  status: number;
  data?: ApiErrorData | unknown;
  fieldErrors?: Record<string, string[]>;

  constructor(message: string, status: number, data?: ApiErrorData | unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;

    if (data && typeof data === 'object' && !Array.isArray(data)) {
      const fieldErrors: Record<string, string[]> = {};
      for (const [key, value] of Object.entries(data as Record<string, unknown>)) {
        if (key === 'detail') continue;
        if (Array.isArray(value)) {
          fieldErrors[key] = value.map((item) => String(item));
        } else if (typeof value === 'string') {
          fieldErrors[key] = [value];
        }
      }
      if (Object.keys(fieldErrors).length > 0) {
        this.fieldErrors = fieldErrors;
      }
    }
  }
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}
