import React, { useId } from 'react';
import { Text, View } from 'react-native';
import Svg, { Circle, Defs, LinearGradient, Stop } from 'react-native-svg';
import { useTheme } from '../../theme';

interface RingProps {
  pct: number;        // 0–100
  color: string;      // solid fallback (used when gradientColors is absent)
  label: string;
  sub?: string;
  size?: number;
  stroke?: number;
  gradientColors?: readonly [string, string]; // [startHex, endHex]
  testID?: string;
}

export function Ring({ pct, color, label, sub, size = 56, stroke = 5, gradientColors, testID }: RingProps) {
  const { colors } = useTheme();
  const uid = useId();
  const gradientId = `rg${uid.replace(/:/g, '')}`;

  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const offset = circumference * (1 - Math.max(0, Math.min(100, pct)) / 100);
  const strokePaint = gradientColors ? `url(#${gradientId})` : color;

  return (
    <View testID={testID} style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}>
      {/* SVG ring is rotated -90° so progress starts at top */}
      <Svg
        width={size}
        height={size}
        style={{ position: 'absolute', transform: [{ rotate: '-90deg' }] }}
      >
        {gradientColors && (
          <Defs>
            <LinearGradient id={gradientId} x1="0%" y1="0%" x2="100%" y2="100%">
              <Stop offset="0%" stopColor={gradientColors[0]} />
              <Stop offset="100%" stopColor={gradientColors[1]} />
            </LinearGradient>
          </Defs>
        )}
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
          stroke={strokePaint}
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
        />
      </Svg>
      <View style={{ alignItems: 'center' }}>
        <Text style={{ fontWeight: '600', fontSize: 14, color: colors.fg1, lineHeight: 16 }}>
          {label}
        </Text>
        {sub && (
          <Text style={{ fontSize: 8, color: colors.fg3, fontWeight: '500', marginTop: 1, letterSpacing: 0.3 }}>
            {sub}
          </Text>
        )}
      </View>
    </View>
  );
}
