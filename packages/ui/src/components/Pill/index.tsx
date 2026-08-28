import React from 'react';
import { Text, View } from 'react-native';
import { useTheme } from '../../theme';

type PillTone = 'neutral' | 'accent' | 'warn' | 'danger' | 'success' | 'info';
type PillSize = 'sm' | 'md';

interface PillProps {
  children: React.ReactNode;
  tone?: PillTone;
  size?: PillSize;
  testID?: string;
}

export function Pill({ children, tone = 'neutral', size = 'md', testID }: PillProps) {
  const { colors } = useTheme();

  const palette: Record<PillTone, { bg: string; fg: string }> = {
    neutral: { bg: colors.bg3,         fg: colors.fg2 },
    accent:  { bg: colors.accentSoft,  fg: colors.accent },
    warn:    { bg: colors.warnSoft,    fg: colors.warn },
    danger:  { bg: colors.dangerSoft,  fg: colors.danger },
    success: { bg: colors.successSoft, fg: colors.success },
    info:    { bg: colors.infoSoft,    fg: colors.info },
  };

  const { bg, fg } = palette[tone];
  const paddingH = size === 'sm' ? 8 : 10;
  const paddingV = size === 'sm' ? 3 : 5;
  const fontSize = size === 'sm' ? 11 : 12;

  return (
    <View
      testID={testID}
      style={{
        alignSelf: 'flex-start',
        backgroundColor: bg,
        borderRadius: 999,
        paddingHorizontal: paddingH,
        paddingVertical: paddingV,
      }}
    >
      <Text style={{ color: fg, fontSize, fontWeight: '600', letterSpacing: 0.1 }}>
        {children}
      </Text>
    </View>
  );
}
