import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { AgentMark, Card, Sparkbars, agentSolid, useTheme } from '@life-agents/ui';
import type { FeaturedBody } from './useHomeSummary';

function formatDelta(value: number | null, unit: string): string | null {
  if (value === null) return null;
  const sign = value > 0 ? '+' : value < 0 ? '−' : '±';
  return `${sign}${Math.abs(value).toFixed(1)} ${unit}`.trim();
}

function StatCell({
  label,
  value,
  unit,
  delta,
}: {
  label: string;
  value: string;
  unit?: string;
  delta: string | null;
}) {
  const { colors } = useTheme();
  return (
    <View style={{ flex: 1 }}>
      <Text
        style={{
          fontSize: 11,
          color: colors.fg3,
          fontWeight: '600',
          letterSpacing: 0.4,
          textTransform: 'uppercase',
        }}
      >
        {label}
      </Text>
      <Text style={{ fontSize: 16, color: colors.fg1, fontWeight: '500', marginTop: 2 }}>
        {value}
        {unit ? (
          <Text style={{ fontSize: 12, color: colors.fg3, fontWeight: '400' }}>{unit}</Text>
        ) : null}
      </Text>
      {delta ? (
        <Text style={{ fontSize: 11, color: colors.fg2, marginTop: 1 }}>
          {delta}
          <Text style={{ fontSize: 10, color: colors.fg3 }}>{' 30d'}</Text>
        </Text>
      ) : null}
    </View>
  );
}

export function BodyCard({ data, onPress }: { data: FeaturedBody | null; onPress: () => void }) {
  const { colors, spacing, typography } = useTheme();
  if (!data) return null;

  const weightDeltaLabel = formatDelta(data.weightDelta30d, 'kg');
  const fatDeltaLabel = formatDelta(data.fatPctDelta30d, '%');
  const muscleDeltaLabel = formatDelta(data.muscleKgDelta30d, 'kg');
  const leanDeltaLabel = formatDelta(data.leanKgDelta30d, 'kg');

  const showFooter = data.fatPct !== null || data.muscleKg !== null || data.leanKg !== null;

  return (
    <Card onPress={onPress}>
      <View style={styles.header}>
        <AgentMark agent="body" size={26} />
        <View style={{ flex: 1 }}>
          <Text style={[typography.bodyEm, { color: colors.fg1 }]}>Body</Text>
          <Text style={[typography.caption, { color: colors.fg3 }]}>
            {data.ageDaysLabel}
            {data.source ? ` · ${data.source}` : ''}
          </Text>
        </View>
        <Text style={{ color: colors.fg3, fontSize: 18 }}>›</Text>
      </View>

      <View
        style={{
          flexDirection: 'row',
          alignItems: 'flex-end',
          gap: spacing.s4,
          marginTop: spacing.s3,
        }}
      >
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 8 }}>
            <Text style={[typography.title1, { color: colors.fg1 }]}>
              {data.weightKg.toFixed(1)} kg
            </Text>
            {data.weightDeltaPrev !== null && data.weightDeltaPrev !== 0 ? (
              <Text style={{ fontSize: 13, color: colors.fg2 }}>
                {data.weightDeltaPrev > 0 ? '↑' : '↓'} {Math.abs(data.weightDeltaPrev).toFixed(1)}{' '}
                kg
              </Text>
            ) : null}
          </View>
          {weightDeltaLabel ? (
            <Text style={[typography.caption, { color: colors.fg2, marginTop: 2 }]}>
              {weightDeltaLabel} · 30d
            </Text>
          ) : null}
        </View>
        {data.sparkWeights.length >= 2 ? (
          <View style={{ width: 90 }}>
            <Sparkbars values={data.sparkWeights} color={agentSolid('body')} />
            <Text
              style={[typography.micro, { color: colors.fg3, textAlign: 'right', marginTop: 4 }]}
            >
              {data.sparkWeights.length} WEIGH-INS
            </Text>
          </View>
        ) : null}
      </View>

      {showFooter ? (
        <View style={[styles.footerRow, { borderTopColor: colors.borderSoft }]}>
          {data.fatPct !== null ? (
            <StatCell label="FAT" value={data.fatPct.toFixed(1)} unit=" %" delta={fatDeltaLabel} />
          ) : null}
          {data.muscleKg !== null ? (
            <StatCell
              label="MUSCLE"
              value={data.muscleKg.toFixed(1)}
              unit=" kg"
              delta={muscleDeltaLabel}
            />
          ) : null}
          {data.leanKg !== null ? (
            <StatCell
              label="LEAN"
              value={data.leanKg.toFixed(1)}
              unit=" kg"
              delta={leanDeltaLabel}
            />
          ) : null}
        </View>
      ) : null}
    </Card>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  footerRow: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 14,
    paddingTop: 12,
    borderTopWidth: 1,
  },
});
