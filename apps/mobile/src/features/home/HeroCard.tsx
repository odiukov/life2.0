import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { CircularProgress, useTheme } from '@life-agents/ui';
import { AGENT_COLOR } from '../dash/agentMeta';
import type { HomeAgent } from './useHomeSummary';
import { usePressScale } from '@/lib/usePressScale';

type Props = {
  data: HomeAgent | null;
  onPress: () => void;
};

export function HeroCard({ data, onPress }: Props) {
  const { colors, radius, spacing, typography } = useTheme();
  const { onPressIn, onPressOut, pressStyle } = usePressScale(0.97);
  const color = AGENT_COLOR.sleep;
  const progress = data?.progress ?? 0;
  const metric = data?.metric ?? null;
  const detail = data?.detail ?? null;
  const hasData = data !== null && metric !== null;

  return (
    <Animated.View style={pressStyle}>
      <Pressable
        onPress={onPress}
        onPressIn={onPressIn}
        onPressOut={onPressOut}
        style={[
          styles.card,
          { backgroundColor: colors.bg2, borderRadius: radius.rLg, borderColor: colors.border, padding: spacing.s4 },
        ]}
      >
        <View style={styles.row}>
          <CircularProgress size={72} progress={progress} color={color} strokeWidth={6}>
            <Text style={[typography.body, { color: colors.fg1, fontWeight: '800' }]}>
              {hasData ? metric : '—'}
            </Text>
          </CircularProgress>

          <View style={styles.info}>
            <Text style={[typography.micro, { color: colors.fg3 }]}>Sleep</Text>
            {hasData ? (
              <>
                <Text style={[typography.body, { color: colors.fg1, fontWeight: '800' }]}>
                  {Math.round(progress * 100)}%{' '}
                  <Text style={[typography.caption, { color: colors.fg3, fontWeight: '400' }]}>of goal</Text>
                </Text>
                {detail ? (
                  <View style={[styles.pills, { marginTop: spacing.s2 }]}>
                    {detail.split('·').map((p) => p.trim()).filter(Boolean).map((pill) => (
                      <View key={pill} style={[styles.pill, { backgroundColor: color + '1a', borderRadius: radius.rXs }]}>
                        <Text style={[typography.micro, { color }]}>{pill}</Text>
                      </View>
                    ))}
                  </View>
                ) : null}
              </>
            ) : (
              <Text style={[typography.caption, { color: colors.fg3, marginTop: 4 }]}>
                No sleep data — tap to log
              </Text>
            )}
          </View>
        </View>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  info: { flex: 1 },
  pills: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  pill: { paddingHorizontal: 8, paddingVertical: 3 },
});
