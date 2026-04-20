export const darkColors = {
  bg0: '#09090b',
  bg1: '#0c0c10',
  bg2: '#141418',
  bg3: '#1a1a22',
  border: '#24242a',
  fg1: '#fafafa',
  fg2: '#a1a1aa',
  fg3: '#52525b',
  accent: '#06b6d4',
  accentHi: '#22d3ee',
  accentSoft: '#073c43',
  accentBorder: '#0e7490',
  success: '#6ee7b7',
  warn: '#fde68a',
  danger: '#fca5a5',
} as const;

export const lightColors = {
  bg0: '#ffffff',
  bg1: '#fafafa',
  bg2: '#f4f4f5',
  bg3: '#e4e4e7',
  border: '#e5e5e5',
  fg1: '#09090b',
  fg2: '#52525b',
  fg3: '#a1a1aa',
  accent: '#0891b2',
  accentHi: '#0e7490',
  accentSoft: '#cffafe',
  accentBorder: '#67e8f9',
  success: '#16a34a',
  warn: '#ca8a04',
  danger: '#dc2626',
} as const;

export type ColorToken = keyof typeof darkColors;
export type ThemeMode = 'dark' | 'light';

export const colors = {
  dark: darkColors,
  light: lightColors,
} satisfies Record<ThemeMode, Record<ColorToken, string>>;
