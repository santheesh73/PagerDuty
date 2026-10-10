const MINUTE = 60;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** "4m 12s", "2h 05m", "3d 4h" — compact durations for response-time metrics. */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < MINUTE) return `${s}s`;
  if (s < HOUR) {
    const m = Math.floor(s / MINUTE);
    const rest = s % MINUTE;
    return rest ? `${m}m ${String(rest).padStart(2, "0")}s` : `${m}m`;
  }
  if (s < DAY) {
    const h = Math.floor(s / HOUR);
    const m = Math.floor((s % HOUR) / MINUTE);
    return `${h}h ${String(m).padStart(2, "0")}m`;
  }
  const d = Math.floor(s / DAY);
  const h = Math.floor((s % DAY) / HOUR);
  return h ? `${d}d ${h}h` : `${d}d`;
}

const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto", style: "short" });

/** "3 min. ago", "in 2 hr." */
export function formatRelative(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return "—";
  const diff = (new Date(iso).getTime() - now) / 1000;
  const abs = Math.abs(diff);
  // `now` ticks every ~15s and server clocks drift, so a fresh event can look slightly in
  // the future. Anything within two minutes ahead is "just now", not "in a moment".
  if (abs < 45 || (diff > 0 && diff < 120)) return "just now";
  if (abs < HOUR) return rtf.format(Math.round(diff / MINUTE), "minute");
  if (abs < DAY) return rtf.format(Math.round(diff / HOUR), "hour");
  return rtf.format(Math.round(diff / DAY), "day");
}

export function formatDateTime(iso: string | null | undefined, timeZone?: string): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone,
  }).format(new Date(iso));
}

export function formatTime(iso: string, timeZone?: string): string {
  return new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", timeZone }).format(
    new Date(iso),
  );
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(value < 0.1 ? 1 : 0)}%`;
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

/** Stable, readable colour slot for a person, so the same user looks the same everywhere. */
export function colorSlot(id: number, slots = 8): number {
  return ((id * 2654435761) >>> 0) % slots;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  return (
    (parts[0]?.[0] ?? "") + (parts.length > 1 ? (parts.at(-1)?.[0] ?? "") : "")
  ).toUpperCase();
}
