/**
 * Formats a unix-ms timestamp as a short relative time string.
 *  - null            → "not synced yet"
 *  - within 60 s     → "just now"
 *  - within 1 h      → "Xm ago"
 *  - within 24 h     → "Xh ago"
 *  - else            → "Xd ago"
 *
 * `now` is injectable for testability; defaults to Date.now().
 */
export function formatRelativeTime(at: number | null, now: number = Date.now()): string {
  if (at == null) return 'not synced yet';
  const delta = Math.max(0, now - at);
  if (delta < 60_000) return 'just now';
  if (delta < 60 * 60_000) return `${Math.floor(delta / 60_000)}m ago`;
  if (delta < 24 * 60 * 60_000) return `${Math.floor(delta / (60 * 60_000))}h ago`;
  return `${Math.floor(delta / (24 * 60 * 60_000))}d ago`;
}
