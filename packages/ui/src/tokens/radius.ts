export const radius = {
  rXs: 6,
  rSm: 8,
  rMd: 12,
  rLg: 16,
  rXl: 22,
} as const;

export type RadiusToken = keyof typeof radius;
