import { describe, it, expect } from 'vitest';
import { formatDateTime, formatRelativeTime, formatDuration, formatIncidentId } from './format';

describe('Format Utilities', () => {
  it('formats dates cleanly and handles null/undefined gracefully', () => {
    expect(formatDateTime(null)).toBe('—');
    expect(formatDateTime(undefined)).toBe('—');
    expect(formatDateTime('invalid-date')).toBe('Invalid date');

    const formatted = formatDateTime('2026-09-21T12:00:00Z');
    expect(formatted).toContain('Sep 21, 2026');
  });

  it('formats relative times cleanly', () => {
    expect(formatRelativeTime(null)).toBe('—');
    expect(formatRelativeTime(undefined)).toBe('—');

    const justNow = new Date(Date.now() - 10 * 1000).toISOString();
    expect(formatRelativeTime(justNow)).toBe('just now');

    const fiveMinsAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString();
    expect(formatRelativeTime(fiveMinsAgo)).toMatch(/5 minutes ago/i);

    const twoHoursAgo = new Date(Date.now() - 2 * 3600 * 1000).toISOString();
    expect(formatRelativeTime(twoHoursAgo)).toMatch(/2 hours ago/i);
  });

  it('formats durations in compact readable units', () => {
    expect(formatDuration(0)).toBe('0m');
    expect(formatDuration(-5)).toBe('0m');
    expect(formatDuration(5)).toBe('5m');
    expect(formatDuration(60)).toBe('1h');
    expect(formatDuration(65)).toBe('1h 5m');
    expect(formatDuration(1440)).toBe('1d');
    expect(formatDuration(1505)).toBe('1d 1h 5m');
  });

  it('formats incident identifiers into canonical format', () => {
    expect(formatIncidentId(1)).toBe('INC-0001');
    expect(formatIncidentId(42)).toBe('INC-0042');
    expect(formatIncidentId('123')).toBe('INC-0123');
    expect(formatIncidentId(10420)).toBe('INC-10420');
    expect(formatIncidentId(null)).toBe('INC-0000');
    expect(formatIncidentId(undefined)).toBe('INC-0000');
    expect(formatIncidentId('custom-abc')).toBe('INC-custom-abc');
  });
});

