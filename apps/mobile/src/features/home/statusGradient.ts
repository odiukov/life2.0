function hslToHex(h: number, s: number, l: number): string {
  const sl = s / 100;
  const ll = l / 100;
  const a = sl * Math.min(ll, 1 - ll);
  const channel = (n: number) => {
    const k = (n + h / 30) % 12;
    const val = ll - a * Math.max(Math.min(k - 3, 9 - k, 1), -1);
    return Math.round(255 * val).toString(16).padStart(2, '0');
  };
  return `#${channel(0)}${channel(8)}${channel(4)}`;
}

export function hslStatusGradient(pct: number): readonly [string, string] {
  const clamped = Math.max(0, Math.min(100, pct));
  const hue = clamped * 1.2;           // 0 → red (0°), 100 → green (120°)
  const startHue = Math.max(0, hue - 20);
  return [
    hslToHex(startHue, 75, 28),        // darker tail
    hslToHex(hue, 85, 55),             // bright leading tip
  ];
}
