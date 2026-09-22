export function formatDurationSeconds(seconds: number | null | undefined, fallback = 'N/A'): string {
  if (seconds === null || seconds === undefined) return fallback;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remSec = Math.round(seconds % 60);
  if (minutes < 60) {
    return remSec > 0 ? `${minutes}m ${remSec}s` : `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remMin = minutes % 60;
  if (hours < 24) {
    return remMin > 0 ? `${hours}h ${remMin}m` : `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  const remHours = hours % 24;
  return remHours > 0 ? `${days}d ${remHours}h` : `${days}d`;
}
