export type ExpiryTone = 'danger' | 'warn' | 'muted';
type T = (key: string, params?: Record<string, string | number>) => string;

/** Compare YYYY-MM-DD calendar dates in the household's time zone. */
export function daysLeft(expiresOn: string, today: Date, timeZone?: string): number {
  const [y = 0, m = 1, d = 1] = expiresOn.split('-').map(Number);
  const parts = timeZone
    ? new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: 'numeric', day: 'numeric' }).formatToParts(today)
    : null;
  const field = (type: string) => Number(parts?.find((part) => part.type === type)?.value);
  const base = parts
    ? Date.UTC(field('year'), field('month') - 1, field('day'))
    : Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  return Math.round((Date.UTC(y, m - 1, d) - base) / 86400000);
}

export function expiryTone(days: number): ExpiryTone {
  if (days <= 0) return 'danger';
  if (days <= 2) return 'warn';
  return 'muted';
}

export function expiryLabel(days: number, t: T): string {
  if (days < 0) return t('kitchen.screen.days.expired');
  if (days === 0) return t('kitchen.screen.days.today');
  if (days === 1) return t('kitchen.screen.days.tomorrow');
  return t('kitchen.screen.days.in', { count: days });
}
