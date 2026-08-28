let pending: string | null = null;

export function storePendingShareUrl(url: string) { pending = url; }

export function consumePendingShareUrl(): string | null {
  const url = pending;
  pending = null;
  return url;
}
