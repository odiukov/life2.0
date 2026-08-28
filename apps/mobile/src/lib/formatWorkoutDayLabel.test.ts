import { formatWorkoutDayLabel } from './formatWorkoutDayLabel';

describe('formatWorkoutDayLabel', () => {
  // Pin "now" to a fixed local-time noon so the day-bucket math is deterministic
  // regardless of the runner's clock.
  const NOW = new Date(2026, 3, 30, 12, 0, 0); // 2026-04-30 12:00 local

  const at = (y: number, m: number, d: number, h = 12) => new Date(y, m, d, h).toISOString();

  it('returns null for null / undefined / unparseable input', () => {
    expect(formatWorkoutDayLabel(null, NOW)).toBeNull();
    expect(formatWorkoutDayLabel(undefined, NOW)).toBeNull();
    expect(formatWorkoutDayLabel('not-a-date', NOW)).toBeNull();
  });

  it('"Today" for the same calendar day, even early morning', () => {
    expect(formatWorkoutDayLabel(at(2026, 3, 30, 6), NOW)).toBe('Today');
    expect(formatWorkoutDayLabel(at(2026, 3, 30, 23), NOW)).toBe('Today');
  });

  it('"Yesterday" for one calendar day earlier', () => {
    expect(formatWorkoutDayLabel(at(2026, 3, 29, 22), NOW)).toBe('Yesterday');
  });

  it('"Nd ago" for 2..6 days earlier', () => {
    expect(formatWorkoutDayLabel(at(2026, 3, 28), NOW)).toBe('2d ago');
    expect(formatWorkoutDayLabel(at(2026, 3, 24), NOW)).toBe('6d ago');
  });

  it('falls back to short date past 6 days', () => {
    expect(formatWorkoutDayLabel(at(2026, 3, 23), NOW)).toBe('Apr 23');
    expect(formatWorkoutDayLabel(at(2026, 2, 15), NOW)).toBe('Mar 15');
  });

  it('clamps future timestamps to "Today"', () => {
    expect(formatWorkoutDayLabel(at(2026, 4, 1), NOW)).toBe('Today');
  });
});
