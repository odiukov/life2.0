let pending: string | null = null;

export function setPrefill(value: string) {
  pending = value;
}

export function consumePrefill(): string | null {
  const v = pending;
  pending = null;
  return v;
}
