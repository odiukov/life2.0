import React from 'react';
import { Pressable, ScrollView, Text } from 'react-native';
import { MiniRing, agentSolid, useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import type { HomeSummary } from '../home/useHomeSummary';
import type { AgentRow } from '../agents/agentStatusRules';
import { AGENT_ORDER } from './agentOrder';

export function MetricChips({
  summary,
  rows,
  onAgent,
  onAll,
}: {
  summary: HomeSummary;
  rows: ReadonlyMap<AgentId, AgentRow>;
  onAgent: (agent: AgentId) => void;
  onAll: () => void;
}) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  const rings = summary.rings;
  const ringData = [
    {
      id: 'ready',
      agent: 'recovery',
      pct: rings?.readyPct,
      value: rings?.readyPct != null ? `${rings.readyPct}%` : '—',
    },
    {
      id: 'hrv',
      agent: 'sleep',
      pct: rings?.hrvPct,
      value:
        rings?.hrvMs != null ? `${rings.hrvMs}` : rings?.hrvPct != null ? `${rings.hrvPct}%` : '—',
    },
    {
      id: 'steps',
      agent: 'workout',
      pct: rings?.stepsPct,
      value: rings?.stepsPct != null ? `${rings.stepsPct}%` : '—',
    },
    {
      id: 'mood',
      agent: 'mood',
      pct: rings?.moodPct,
      value: rings?.moodPct != null ? `${rings.moodPct}%` : '—',
    },
  ] as const;
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={{ gap: 10, alignItems: 'center' }}
    >
      {ringData.map(({ id, agent, pct, value }) => (
        <Pressable
          key={id}
          testID={`ring-${id}`}
          accessibilityRole="button"
          onPress={() => onAgent(agent)}
        >
          <MiniRing
            pct={pct ?? 0}
            color={agentSolid(agent)}
            value={value}
            label={t(`me.rings.${id}`)}
          />
        </Pressable>
      ))}
      {AGENT_ORDER.map((id) => {
        const tile = summary.agents.find((a) => a.agent === id);
        const unavailable = summary.unavailable.includes(id);
        const value = unavailable
          ? '—'
          : rows.get(id)?.status === 'needs_setup'
            ? '＋'
            : (tile?.metric ?? '—');
        return (
          <Pressable
            key={id}
            testID={`chip-${id}`}
            accessibilityRole="button"
            onPress={() => onAgent(id)}
            style={{
              paddingVertical: 6,
              paddingHorizontal: 10,
              borderRadius: 999,
              backgroundColor: colors.bg3,
              borderWidth: tile && !unavailable ? 1 : 0,
              borderColor: agentSolid(id),
            }}
          >
            <Text style={{ color: colors.fg2 }}>{t(`dashboard.agent_labels.${id}`)}</Text>
            <Text style={{ color: colors.fg1 }}>{value}</Text>
          </Pressable>
        );
      })}
      <Pressable testID="chip-all" accessibilityRole="button" onPress={onAll}>
        <Text style={{ color: colors.fg2 }}>{t('me.all')}</Text>
      </Pressable>
    </ScrollView>
  );
}
