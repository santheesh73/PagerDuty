// Error reporting is opt-in: with no VITE_SENTRY_DSN nothing is imported, nothing is sent, and
// the SDK is not even downloaded (it is a separate chunk behind a dynamic import).
const SECRET =
  /pass|secret|token|authorization|cookie|csrf|session|api[-_]?key|routing[-_]?key|integration/i;

export function scrub<T>(value: T): T {
  if (Array.isArray(value)) return value.map(scrub) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [
        k,
        SECRET.test(k) ? "[Filtered]" : scrub(v),
      ]),
    ) as T;
  }
  return value;
}

type EventLike = {
  request?: { cookies?: unknown; headers?: Record<string, string>; data?: unknown } & Record<
    string,
    unknown
  >;
  user?: unknown;
} & Record<string, unknown>;

export function beforeSend<E extends EventLike>(event: E): E {
  if (event.request) {
    delete event.request.cookies;
    delete event.request.data;
    delete event.request.headers;
  }
  delete event.user;
  return scrub(event);
}

export async function initErrorReporting(): Promise<void> {
  const dsn = import.meta.env.VITE_SENTRY_DSN;
  if (!dsn) return;
  const Sentry = await import("@sentry/react");
  Sentry.init({
    dsn,
    release: import.meta.env.VITE_RELEASE || undefined, // the git SHA, set at build time
    environment: import.meta.env.VITE_SENTRY_ENVIRONMENT || "production",
    // Collect nothing by default; beforeSend below is a second line of defence.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
    },
    tracesSampleRate: 0,
    beforeSend: (event) => beforeSend(event as unknown as EventLike) as unknown as typeof event,
  });
}
