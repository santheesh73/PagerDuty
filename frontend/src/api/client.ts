/**
 * The one fetch wrapper. Every request goes through here so that:
 *  - session cookies are always sent (same-origin),
 *  - unsafe methods carry Django's CSRF token,
 *  - the backend's error envelope becomes a typed ApiError.
 */

export interface ErrorEnvelope {
  error: { code: string; message: string; details: Record<string, unknown> };
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(
    status: number,
    code: string,
    message: string,
    details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  /** First field-level validation message, if any — handy for inline form errors. */
  fieldError(field: string): string | undefined {
    const value = this.details[field];
    if (Array.isArray(value)) return String(value[0]);
    if (typeof value === "string") return value;
    return undefined;
  }
}

const BASE = "/api/v1";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function readCookie(name: string): string | undefined {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`))
    ?.split("=")[1];
}

async function ensureCsrfCookie(): Promise<string | undefined> {
  if (!readCookie("csrftoken")) {
    await fetch(`${BASE}/auth/csrf/`, { credentials: "same-origin" });
  }
  return readCookie("csrftoken");
}

type Query = Record<string, string | number | boolean | null | undefined>;

export interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Query;
  signal?: AbortSignal;
}

export function buildUrl(path: string, query?: Query): string {
  // Absolute URLs (e.g. DRF pagination links) are reduced to path + query: requests must stay
  // on this origin for the session cookie, whatever host the backend thinks it is.
  if (/^https?:\/\//.test(path)) {
    const absolute = new URL(path);
    path = absolute.pathname + absolute.search;
  }
  const url = path.startsWith(BASE) ? path : `${BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}${url.includes("?") ? "&" : "?"}${qs}` : url;
}

export async function api<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? "GET";
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (UNSAFE.has(method)) {
    const token = await ensureCsrfCookie();
    if (token) headers["X-CSRFToken"] = token;
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, options.query), {
      method,
      headers,
      credentials: "same-origin",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    });
  } catch (cause) {
    if ((cause as Error).name === "AbortError") throw cause;
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection.");
  }

  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = (data as ErrorEnvelope | null)?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? `http_${response.status}`,
      envelope?.message ?? response.statusText ?? "Request failed",
      envelope?.details ?? {},
    );
  }
  return data as T;
}
