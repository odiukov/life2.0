import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { AgentMark, useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import type { AgentRow } from '../agents/agentStatusRules';
import type { HomeSummary } from '../home/useHomeSummary';
import { AGENT_ORDER } from './agentOrder';

function AgentTile({
  id,
  value,
  hint,
  row,
  onPress,
}: {
  id: AgentId;
  value: string;
  hint: string;
  row: AgentRow | undefined;
  onPress: (id: AgentId) => void;
}) {
  const { colors, radius, typography } = useTheme();
  const t = useT(appLocale());

  const isNeedsSetup = row?.status === 'needs_setup' && row.cta != null;
  const ctaKind = row?.cta?.kind;
  // Table of CTA-pill presentation. `connect`/`upload` intentionally share the
  // `info` colour family — both signal "user must wire up an external thing".
  const pill =
    ctaKind === 'integrations'
      ? { label: t('me.connect'), fg: colors.info, bg: colors.infoSoft }
      : ctaKind === 'chat-prefill'
        ? { label: t('me.log'), fg: colors.accent, bg: colors.accentSoft }
        : ctaKind === 'finance-upload'
          ? { label: t('me.upload'), fg: colors.info, bg: colors.infoSoft }
          : null;

  const displayHint = row?.hint ?? hint;
  const hintColor = isNeedsSetup ? colors.fg2 : colors.fg3;
  const valueText = isNeedsSetup ? '—' : value;
  const valueColor = isNeedsSetup ? colors.fg3 : colors.fg1;

  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => onPress(id)}
      style={({ pressed }) => [
        styles.tile,
        {
          backgroundColor: isNeedsSetup ? colors.bg1 : colors.bg2,
          borderColor: isNeedsSetup ? colors.borderSoft : colors.border,
          borderStyle: isNeedsSetup ? 'dashed' : 'solid',
          borderRadius: radius.rMd,
          opacity: pressed ? 0.85 : 1,
        },
      ]}
    >
      <View style={{ opacity: isNeedsSetup ? 0.55 : 1 }}>
        <AgentMark agent={id} size={34} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={styles.tileLabelRow}>
          <Text
            numberOfLines={1}
            style={[
              typography.caption,
              { color: colors.fg3, fontWeight: '600', flexShrink: 1, minWidth: 0 },
            ]}
          >
            {t(`dashboard.agent_labels.${id}`)}
          </Text>
          {pill ? (
            <View
              style={{
                paddingHorizontal: 6,
                paddingVertical: 2,
                borderRadius: radius.rXs,
                backgroundColor: pill.bg,
                flexShrink: 0,
              }}
            >
              <Text style={[typography.micro, { color: pill.fg, fontWeight: '700' }]}>
                {pill.label}
              </Text>
            </View>
          ) : null}
        </View>
        <Text
          numberOfLines={1}
          style={{
            fontFamily: typography.title2.fontFamily,
            fontSize: 15,
            color: valueColor,
            fontWeight: '600',
            letterSpacing: -0.2,
            marginTop: 1,
          }}
        >
          {valueText}
        </Text>
        {displayHint ? (
          <Text
            numberOfLines={1}
            style={{
              fontSize: 11,
              color: hintColor,
              marginTop: 1,
              fontWeight: '400',
            }}
          >
            {displayHint}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

export function AllAgentsGrid({
  summary,
  rows,
  onPick,
}: {
  summary?: HomeSummary;
  rows?: ReadonlyMap<AgentId, AgentRow>;
  onPick: (id: AgentId) => void;
}) {
  const bucket = (id: AgentId) => {
    const row = rows?.get(id);
    if (row?.status === 'ready') return 0;
    if (!row || row.status === 'no_data') return 1;
    return row.cta?.kind === 'chat-prefill' ? 2 : 3;
  };
  const ids = [...AGENT_ORDER].sort((a, b) => bucket(a) - bucket(b));
  return (
    <View style={styles.grid}>
      {ids
        .filter((id) => !summary?.unavailable.includes(id))
        .map((id) => {
          const agent = summary?.agents.find((a) => a.agent === id);
          return (
            <View key={id} style={styles.gridCell}>
              <AgentTile
                id={id}
                value={agent?.metric ?? '—'}
                hint={agent?.detail ?? ''}
                row={rows?.get(id)}
                onPress={onPick}
              />
            </View>
          );
        })}
    </View>
  );
}
const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: -4 },
  gridCell: { paddingBottom: 8, paddingHorizontal: 4, width: '50%' },
  tile: {
    alignItems: 'center',
    borderWidth: 1,
    flexDirection: 'row',
    gap: 12,
    minHeight: 76,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  tileLabelRow: {
    alignItems: 'baseline',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
});
