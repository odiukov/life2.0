import { daysLeft, expiryTone } from './expiry';

it.each([
  ['2026-10-12', -1, 'danger'],
  ['2026-10-13', 0, 'danger'],
  ['2026-10-14', 1, 'warn'],
  ['2026-10-15', 2, 'warn'],
  ['2026-10-16', 3, 'muted'],
] as const)('compares %s as %d days with %s tone', (iso, days, tone) => {
  expect(daysLeft(iso, new Date('2026-10-13T22:30:00Z'), 'Europe/Lisbon')).toBe(days);
  expect(expiryTone(days)).toBe(tone);
});

it('uses household day across device and UTC boundaries', () => {
  const now = new Date('2026-10-13T22:30:00Z');
  expect(daysLeft('2026-10-14', now, 'Europe/Lisbon')).toBe(1);
  expect(daysLeft('2026-10-14', now, 'Europe/Helsinki')).toBe(0);
});
