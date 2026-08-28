import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import Svg, { Circle } from 'react-native-svg';
import { useTheme } from '@life-agents/ui';
import type { AgentId } from '@life-agents/ui';
import type { HistoryPoint } from './useAgentDetail';

type ChartType = 'bar' | 'line' | 'calendar';

const CHART_TYPE: Record<AgentId, ChartType> = {
  sleep: 'bar',
  workout: 'bar',
  nutrition: 'bar',
  mood: 'line',
  habits: 'calendar',
  recovery: 'line',
  medication: 'calendar',
  finance: 'bar',
  calendar: 'bar',
  home: 'bar',
  body: 'line',
};

type Props = {
  history: HistoryPoint[];
  color: string;
  agentId: AgentId;
};

function CalendarStrip({ history, color }: { history: HistoryPoint[]; color: string }) {
  const { colors, spacing, typography } = useTheme();
  const days = history.slice(-30);
  const CIRCLE = 9;
  const GAP = 3;

  return (
    <View style={[styles.chartContainer, { padding: spacing.s3 }]}>
      <Text style={[typography.micro, { color: colors.fg3, marginBottom: 8 }]}>30 days</Text>
      <Svg
        width={(CIRCLE + GAP) * 15}
        height={(CIRCLE + GAP) * 2 + CIRCLE}
        style={{ overflow: 'visible' }}
      >
        {days.map((d, i) => {
          const col = i % 15;
          const row = Math.floor(i / 15);
          const cx = col * (CIRCLE + GAP) + CIRCLE / 2;
          const cy = row * (CIRCLE + GAP) + CIRCLE / 2;
          const filled = d.value > 0;
          return (
            <Circle
              key={d.date}
              cx={cx}
              cy={cy}
              r={CIRCLE / 2}
              fill={filled ? color : colors.bg3}
              stroke={filled ? color : colors.border}
              strokeWidth={1}
            />
          );
        })}
      </Svg>
    </View>
  );
}

function BarChartView({
  history,
  color,
  target,
}: {
  history: HistoryPoint[];
  color: string;
  target?: { value: number; label: string };
}) {
  const { colors, spacing, typography } = useTheme();
  // @ts-ignore — no bundled type declarations for gifted-charts
  const { BarChart } = require('react-native-gifted-charts');

  const dataMax = history.reduce((m, h) => Math.max(m, h.value), 0.1);
  const maxVal = target ? Math.max(dataMax, target.value) : dataMax;
  const barData = history.map((h, i) => ({
    value: h.value,
    label: new Date(h.date).toLocaleDateString('en', { weekday: 'short' }).slice(0, 2),
    frontColor: i === history.length - 1 ? color : color + '60',
    gradientColor: color + '20',
    topLabelComponent:
      i === history.length - 1
        ? () => (
            <Text numberOfLines={1} style={{ fontSize: 8, color, marginBottom: 2 }}>
              {h.label}
            </Text>
          )
        : undefined,
  }));

  return (
    <View style={[styles.chartContainer, { padding: spacing.s3 }]}>
      <Text style={[typography.micro, { color: colors.fg3, marginBottom: 8 }]}>7 days</Text>
      <BarChart
        data={barData}
        height={60}
        barWidth={22}
        spacing={6}
        roundedTop
        hideRules
        hideYAxisText
        xAxisColor={colors.border}
        xAxisLabelTextStyle={{ color: colors.fg3, fontSize: 9 }}
        showGradient
        isAnimated
        animationDuration={400}
        noOfSections={3}
        maxValue={maxVal * 1.3}
        showReferenceLine1={target !== undefined}
        referenceLine1Position={target?.value}
        referenceLine1Config={{
          color: colors.fg3,
          dashWidth: 3,
          dashGap: 3,
          thickness: 1,
          labelText: target?.label,
          labelTextStyle: { color: colors.fg3, fontSize: 9 },
        }}
      />
    </View>
  );
}

function LineChartView({ history, color }: { history: HistoryPoint[]; color: string }) {
  const { colors, spacing, typography } = useTheme();
  // @ts-ignore — no bundled type declarations for gifted-charts
  const { LineChart } = require('react-native-gifted-charts');

  const lineData = history.map((h) => ({
    value: h.value,
    dataPointColor: color,
  }));

  return (
    <View style={[styles.chartContainer, { padding: spacing.s3 }]}>
      <Text style={[typography.micro, { color: colors.fg3, marginBottom: 8 }]}>7 days</Text>
      <LineChart
        data={lineData}
        height={60}
        color={color}
        thickness={1.5}
        startFillColor={color + '40'}
        endFillColor={color + '05'}
        areaChart
        hideRules
        hideYAxisText
        xAxisColor={colors.border}
        dataPointsColor={color}
        isAnimated
        animationDuration={400}
      />
    </View>
  );
}

export function AgentDetailChart({ history, color, agentId }: Props) {
  const { colors, radius, spacing } = useTheme();

  if (!history.length) return null;

  const chartType = CHART_TYPE[agentId] ?? 'bar';

  return (
    <Animated.View
      entering={FadeInDown.duration(320).delay(180)}
      style={[
        styles.wrapper,
        {
          backgroundColor: colors.bg3,
          borderRadius: radius.rMd,
          marginBottom: spacing.s3,
          overflow: 'hidden',
        },
      ]}
    >
      {chartType === 'calendar' && <CalendarStrip history={history} color={color} />}
      {chartType === 'bar' && (
        <BarChartView
          history={history}
          color={color}
          target={agentId === 'workout' ? { value: 60, label: '1h' } : undefined}
        />
      )}
      {chartType === 'line' && <LineChartView history={history} color={color} />}
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrapper: {},
  chartContainer: {},
});
