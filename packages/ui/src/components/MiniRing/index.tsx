import React from 'react';
import { Text, View } from 'react-native';
import Svg, { Circle } from 'react-native-svg';
import { useTheme } from '../../theme';

interface MiniRingProps {
  pct: number;
  color: string;
  value: string;
  label: string;
  size?: number;
  stroke?: number;
  testID?: string;
}

export function MiniRing({
  pct,
  color,
  value,
  label,
  size = 60,
  stroke = 5,
  testID,
}: MiniRingProps) {
  const { colors, typography } = useTheme();
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - Math.max(0, Math.min(100, pct)) / 100);

  return (
    <View testID={testID} style={{ alignItems: 'center', gap: 6 }}>
      <View style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
        <Svg
          width={size}
          height={size}
          style={{ position: 'absolute', transform: [{ rotate: '-90deg' }] }}
        >
          <Circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={colors.bg3}
            strokeWidth={stroke}
          />
          <Circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeDasharray={c}
            strokeDashoffset={offset}
            strokeLinecap="round"
          />
        </Svg>
        <Text
          style={{
            fontFamily: typography.mono.fontFamily,
            fontWeight: '600',
            fontSize: 13,
            color: colors.fg1,
            letterSpacing: -0.3,
          }}
        >
          {value}
        </Text>
      </View>
      <Text
        style={{
          fontSize: 10,
          color: colors.fg3,
          fontWeight: '600',
          letterSpacing: 0.5,
          textTransform: 'uppercase',
        }}
      >
        {label}
      </Text>
    </View>
  );
}
