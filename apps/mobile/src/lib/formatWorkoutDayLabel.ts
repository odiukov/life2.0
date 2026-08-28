/**
 * Calendar-day label for the "last workout" timestamp on the Home Training card.
 *
 *  - same calendar day as `now` → "Today"
 *  - one day before             → "Yesterday"
 *  - 2..6 days before           → "Nd ago"
 *  - 7+ days before             → short month-day, e.g. "Apr 24"
 *  - null / undefined           → null (caller decides fallback)
 *
 * Day boundaries are computed in the device's local timezone — that matches the
 * user's mental model ("the workout I did yesterday") and lines up with how the
 * backend buckets days for the sparkline.
 */
export function formatWorkoutDayLabel(
  at: string | null | undefined,
  now: Date = new Date(),
): string | null {
  if (!at) return null;
  const ts = new Date(at);
  if (Number.isNaN(ts.getTime())) return null;

  const startOfDay = (d: Date) => {
    const x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
  };

  const days = Math.floor(
    (startOfDay(now).getTime() - startOfDay(ts).getTime()) / (24 * 60 * 60_000),
  );

  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  return ts.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}
