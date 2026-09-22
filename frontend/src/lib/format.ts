/**
 * Date/time and duration formatting utilities using native Intl APIs.
 * Pure display formatting: does not make domain or scheduling decisions.
 */

/**
 * Formats an ISO datetime string into a localized readable date & time.
 * Example output: "Sep 21, 2026, 2:30 PM UTC"
 */
export function formatDateTime(
  dateStr: string | null | undefined,
  options?: Intl.DateTimeFormatOptions,
  locale = 'en-US'
): string {
  if (!dateStr) return '—';

  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return 'Invalid date';

  const defaultOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'UTC',
    timeZoneName: 'short',
    ...options,
  };

  return new Intl.DateTimeFormat(locale, defaultOptions).format(date);
}

/**
 * Formats an ISO datetime string into a relative time string (e.g. "5m ago", "in 2h", "just now").
 */
export function formatRelativeTime(dateStr: string | null | undefined): string {
  if (!dateStr) return '—';

  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return 'Invalid date';

  const now = Date.now();
  const diffInSeconds = Math.round((date.getTime() - now) / 1000);

  const absDiff = Math.abs(diffInSeconds);
  if (absDiff < 45) {
    return 'just now';
  }

  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });

  if (absDiff < 3600) {
    const minutes = Math.round(diffInSeconds / 60);
    return rtf.format(minutes, 'minute');
  }

  if (absDiff < 86400) {
    const hours = Math.round(diffInSeconds / 3600);
    return rtf.format(hours, 'hour');
  }

  const days = Math.round(diffInSeconds / 86400);
  return rtf.format(days, 'day');
}

/**
 * Formats duration in minutes or seconds into human-readable compact string.
 * e.g. 5 -> "5m", 65 -> "1h 5m", 1440 -> "1d"
 */
export function formatDuration(minutes: number): string {
  if (minutes < 0 || isNaN(minutes)) return '0m';
  if (minutes === 0) return '0m';

  const days = Math.floor(minutes / 1440);
  const remainingMinutesAfterDays = minutes % 1440;
  const hours = Math.floor(remainingMinutesAfterDays / 60);
  const remainingMinutes = remainingMinutesAfterDays % 60;

  const parts: string[] = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  if (remainingMinutes > 0 || parts.length === 0) parts.push(`${remainingMinutes}m`);

  return parts.join(' ');
}

/**
 * Standardizes display identifier for operational incidents (e.g. "INC-0042").
 * Preserves the database numeric ID internally while providing consistent, professional presentation.
 */
export function formatIncidentId(id: number | string | null | undefined): string {
  if (id === null || id === undefined) return 'INC-0000';
  const num = typeof id === 'string' ? parseInt(id, 10) : id;
  if (isNaN(num)) return `INC-${id}`;
  return `INC-${String(num).padStart(4, '0')}`;
}
