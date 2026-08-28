import React from 'react';
import { Text, View } from 'react-native';
import { useTheme } from '../../theme';

interface StatRowProps {
  label: string;
  value: string;
  unit?: string;
  hint?: string;
  bar?: { pct: number };
  tint?: string;
  testID?: string;
}

export function StatRow({ label, value, unit, hint, bar, tint, testID }: StatRowProps) {
  const { colors, typography } = useTheme();
  const barColor = tint ?? colors.accent;
  return (
    <View testID={testID} style={{ flex: 1, minWidth: 0 }}>
      <Text
        style={{
          fontSize: 10.5,
          color: colors.fg3,
          fontWeight: '600',
          letterSpacing: 0.5,
          textTransform: 'uppercase',
        }}
      >
        {label}
      </Text>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 4, marginTop: 4 }}>
        <Text
          style={{
            fontFamily: typography.mono.fontFamily,
            fontSize: 20,
            color: colors.fg1,
            fontWeight: '500',
            letterSpacing: -0.3,
          }}
        >
          {value}
        </Text>
        {unit && <Text style={{ fontSize: 11, color: colors.fg3 }}>{unit}</Text>}
      </View>
      {hint && <Text style={{ fontSize: 11, color: colors.fg3, marginTop: 2 }}>{hint}</Text>}
      {bar && (
        <View
          style={{
            marginTop: 8,
            height: 3,
            backgroundColor: colors.bg3,
            borderRadius: 2,
            overflow: 'hidden',
          }}
        >
          <View
            style={{
              width: `${Math.max(0, Math.min(100, bar.pct))}%`,
              height: '100%',
              backgroundColor: barColor,
            }}
          />
        </View>
      )}
    </View>
  );
}
