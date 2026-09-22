import { describe, it, expect } from 'vitest';
import { formatDurationSeconds } from './duration';

describe('formatDurationSeconds', () => {
  it('handles null and undefined values', () => {
    expect(formatDurationSeconds(null)).toBe('N/A');
    expect(formatDurationSeconds(undefined)).toBe('N/A');
    expect(formatDurationSeconds(null, '—')).toBe('—');
  });

  it('formats seconds under one minute', () => {
    expect(formatDurationSeconds(0)).toBe('0s');
    expect(formatDurationSeconds(42)).toBe('42s');
    expect(formatDurationSeconds(59.4)).toBe('59s');
  });

  it('formats minutes and seconds', () => {
    expect(formatDurationSeconds(60)).toBe('1m');
    expect(formatDurationSeconds(125)).toBe('2m 5s');
    expect(formatDurationSeconds(3540)).toBe('59m');
  });

  it('formats hours and minutes', () => {
    expect(formatDurationSeconds(3600)).toBe('1h');
    expect(formatDurationSeconds(3660)).toBe('1h 1m');
    expect(formatDurationSeconds(7320)).toBe('2h 2m');
  });

  it('formats days and hours', () => {
    expect(formatDurationSeconds(86400)).toBe('1d');
    expect(formatDurationSeconds(90000)).toBe('1d 1h');
  });
});
