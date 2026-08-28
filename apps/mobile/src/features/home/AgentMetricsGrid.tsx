import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { useTheme } from '@life-agents/ui';
import type { AgentId } from '@life-agents/ui';

type MetricConfig = {
  label: string;
  unit?: string;
  deltaKey?: string;
  higherIsBetter: boolean;
  format?: (v: number) => string;
};

function fmtHours(h: number): string {
  const hrs = Math.floor(h);
  const mins = Math.round((h - hrs) * 60);
  return mins > 0 ? `${hrs}h ${mins}m` : `${hrs}h`;
}

function fmtPct(v: number): string {
  return `${Math.round(v * 100)}%`;
}

const METRICS_CONFIG: Partial<Record<AgentId, Record<string, MetricConfig>>> = {
  sleep: {
    deep_hours:     { label: 'Deep Sleep', higherIsBetter: true, format: fmtHours },
    rem_hours:      { label: 'REM', higherIsBetter: true, format: fmtHours },
    hrv:            { label: 'HRV', unit: 'ms', deltaKey: 'hrv_delta', higherIsBetter: true },
    efficiency_pct: { label: 'Efficiency', unit: '%', higherIsBetter: true },
  },
  workout: {
    duration_min:  { label: 'Duration', unit: 'min', higherIsBetter: true },
    distance_km:   { label: 'Distance', unit: 'km', higherIsBetter: true },
    kcal:          { label: 'Calories', unit: 'kcal', higherIsBetter: true },
  },
  nutrition: {
    protein_g: { label: 'Protein', unit: 'g', higherIsBetter: true },
    carbs_g:   { label: 'Carbs', unit: 'g', higherIsBetter: true },
    fat_g:     { label: 'Fat', unit: 'g', higherIsBetter: false },
    goal_kcal: { label: 'Goal', unit: 'kcal', higherIsBetter: true },
  },
  mood: {
    energy:  { label: 'Energy', unit: '/10', higherIsBetter: true },
    stress:  { label: 'Stress', unit: '/10', higherIsBetter: false },
    valence: { label: 'Valence', higherIsBetter: true },
    top_tag: { label: 'Top Tag', higherIsBetter: true },
  },
  habits: {
    streak:        { label: 'Streak', unit: 'days', higherIsBetter: true },
    completion_7d: { label: '7-day rate', higherIsBetter: true, format: fmtPct },
    active_count:  { label: 'Active', unit: 'habits', higherIsBetter: true },
  },
  recovery: {
    hrv_weekly_avg: { label: 'HRV', unit: 'ms', deltaKey: 'hrv_weekly_avg_delta_pct', higherIsBetter: true },
    resting_hr:     { label: 'RHR', unit: 'bpm', deltaKey: 'resting_hr_delta_pct', higherIsBetter: false },
    stress_avg:     { label: 'Stress', higherIsBetter: false },
    body_battery:   { label: 'Battery', unit: '%', higherIsBetter: true },
  },
  medication: {
    adherence_7d:  { label: 'Adherence', higherIsBetter: true, format: fmtPct },
    active_count:  { label: 'Active', unit: 'meds', higherIsBetter: true },
  },
  finance: {
    spent_week:   { label: 'This Week', unit: '$', higherIsBetter: false },
    runway_days:  { label: 'Runway', unit: 'days', higherIsBetter: true },
    top_category: { label: 'Top Category', higherIsBetter: true },
  },
};

function deltaColor(delta: number, higherIsBetter: boolean, colors: any): string {
  const positive = higherIsBetter ? delta > 0 : delta < 0;
  const abs = Math.abs(delta);
  if (abs < 2) return colors.fg3;
  return positive ? '#10b981' : '#f59e0b';
}

type Props = {
  metrics: Record<string, number | string | string[]>;
  color: string;
  agentId: AgentId;
};

export function AgentMetricsGrid({ metrics, color, agentId }: Props) {
  const { colors, radius, spacing, typography } = useTheme();
  const config = METRICS_CONFIG[agentId];
  if (!config || Object.keys(metrics).length === 0) return null;

  const entries = Object.entries(config).filter(([key]) => metrics[key] !== undefined);
  if (entries.length === 0) return null;

  return (
    <Animated.View entering={FadeInDown.duration(320).delay(120)} style={[styles.grid, { marginBottom: spacing.s3 }]}>
      {entries.map(([key, cfg]) => {
        const raw = metrics[key];
        if (raw === undefined) return null;
        const isString = typeof raw === 'string';
        const numVal = typeof raw === 'number' ? raw : null;
        const displayVal = isString
          ? raw
          : cfg.format && numVal !== null
          ? cfg.format(numVal)
          : `${numVal ?? '—'}${cfg.unit ? ` ${cfg.unit}` : ''}`;

        const deltaRaw = cfg.deltaKey ? metrics[cfg.deltaKey] : undefined;
        const delta = typeof deltaRaw === 'number' ? deltaRaw : null;

        return (
          <View
            key={key}
            style={[
              styles.cell,
              {
                backgroundColor: colors.bg3,
                borderRadius: radius.rSm,
                padding: spacing.s3,
              },
            ]}
          >
            <Text style={[typography.micro, { color: colors.fg3, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 3 }]}>
              {cfg.label}
            </Text>
            <Text style={[typography.title2, { color: colors.fg1, fontWeight: '700' }]} numberOfLines={1}>
              {displayVal}
            </Text>
            {delta !== null && (
              <Text style={[typography.micro, { color: deltaColor(delta, cfg.higherIsBetter, colors), marginTop: 2 }]}>
                {delta > 0 ? '+' : ''}{delta.toFixed(1)}
              </Text>
            )}
          </View>
        );
      })}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  cell: { width: '47.5%' },
});
