import { formatRelativeTime } from './formatRelativeTime';

describe('formatRelativeTime', () => {
  const NOW = 1_700_000_000_000;

  it('returns "not synced yet" for null', () => {
    expect(formatRelativeTime(null, NOW)).toBe('not synced yet');
  });

  it('returns "just now" within 60 seconds', () => {
    expect(formatRelativeTime(NOW - 1_000, NOW)).toBe('just now');
    expect(formatRelativeTime(NOW - 59_000, NOW)).toBe('just now');
  });

  it('returns minutes for < 1 hour', () => {
    expect(formatRelativeTime(NOW - 60_000, NOW)).toBe('1m ago');
    expect(formatRelativeTime(NOW - 5 * 60_000, NOW)).toBe('5m ago');
    expect(formatRelativeTime(NOW - 59 * 60_000, NOW)).toBe('59m ago');
  });

  it('returns hours for < 24 hours', () => {
    expect(formatRelativeTime(NOW - 60 * 60_000, NOW)).toBe('1h ago');
    expect(formatRelativeTime(NOW - 23 * 60 * 60_000, NOW)).toBe('23h ago');
  });

  it('returns days for >= 24 hours', () => {
    expect(formatRelativeTime(NOW - 24 * 60 * 60_000, NOW)).toBe('1d ago');
    expect(formatRelativeTime(NOW - 7 * 24 * 60 * 60_000, NOW)).toBe('7d ago');
  });

  it('clamps negative deltas (clock drift) to "just now"', () => {
    expect(formatRelativeTime(NOW + 5_000, NOW)).toBe('just now');
  });
});
