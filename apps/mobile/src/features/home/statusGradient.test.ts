import { hslStatusGradient } from './statusGradient';

test('returns two hex strings', () => {
  const [start, end] = hslStatusGradient(50);
  expect(start).toMatch(/^#[0-9a-f]{6}$/i);
  expect(end).toMatch(/^#[0-9a-f]{6}$/i);
});

test('pct=0 produces a red end color (hue near 0)', () => {
  const [, end] = hslStatusGradient(0);
  // hue=0 → red channel dominant; R > 128, G < 100
  const r = parseInt(end.slice(1, 3), 16);
  const g = parseInt(end.slice(3, 5), 16);
  expect(r).toBeGreaterThan(128);
  expect(g).toBeLessThan(100);
});

test('pct=100 produces a green end color (hue near 120)', () => {
  const [, end] = hslStatusGradient(100);
  // hue=120 → green channel dominant; G > 128, R < 100
  const r = parseInt(end.slice(1, 3), 16);
  const g = parseInt(end.slice(3, 5), 16);
  expect(g).toBeGreaterThan(128);
  expect(r).toBeLessThan(100);
});

test('clamps values below 0 to red', () => {
  const [, end0] = hslStatusGradient(0);
  const [, endNeg] = hslStatusGradient(-20);
  expect(endNeg).toBe(end0);
});

test('clamps values above 100 to green', () => {
  const [, end100] = hslStatusGradient(100);
  const [, endOver] = hslStatusGradient(120);
  expect(endOver).toBe(end100);
});

test('start color is darker than end color (lower lightness)', () => {
  const [start, end] = hslStatusGradient(70);
  // Sum of RGB components as proxy for brightness
  const brightness = (hex: string) =>
    parseInt(hex.slice(1, 3), 16) + parseInt(hex.slice(3, 5), 16) + parseInt(hex.slice(5, 7), 16);
  expect(brightness(start)).toBeLessThan(brightness(end));
});
