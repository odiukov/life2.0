import React, { createContext, useMemo } from 'react';
import { colors as colorsByMode, ThemeMode } from '../tokens/colors';
import { typography } from '../tokens/typography';
import { spacing } from '../tokens/spacing';
import { radius } from '../tokens/radius';

type ThemeValue = {
  mode: ThemeMode;
  colors: (typeof colorsByMode)['dark'];
  typography: typeof typography;
  spacing: typeof spacing;
  radius: typeof radius;
};

export const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({
  mode = 'dark',
  children,
}: {
  mode?: ThemeMode;
  children: React.ReactNode;
}) {
  const value = useMemo<ThemeValue>(
    () => ({ mode, colors: colorsByMode[mode], typography, spacing, radius }),
    [mode],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}
