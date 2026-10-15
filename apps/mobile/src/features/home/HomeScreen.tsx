import { UnavailableNote } from './UnavailableNote';
import React, { useEffect, useMemo, useState } from 'react';
import {
  AppState,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  AgentMark,
  Icon,
  MiniRing,
  Screen,
  ScreenState,
  agentSolid,
  useTheme,
} from '@life-agents/ui';
import type { AgentId } from '@life-agents/ui';
import { useSession } from '@/features/auth/useSession';
import { AGENT_COPY } from '@/features/agents/agentCopy';
import type { AgentRow } from '@/features/agents/agentStatusRules';
import { useAgentStatusRows } from '@/features/agents/useAgentStatusRows';
import { dispatchTilePress } from '@/features/agents/agentTileDispatch';
import { IntegrationSheet } from '@/features/integrations/IntegrationSheet';
import type { IntegrationId } from '@/features/integrations/store';
import { useRouter } from 'expo-router';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { SettingsSheet } from '../more/SettingsSheet';
import { AgentDetailSheet } from './AgentDetailSheet';
import { useHomeSummary } from './useHomeSummary';
import { badgeText } from '@/features/inbox/badge';
import { useInbox } from '@/features/inbox/useInbox';
import type { HomeAgent } from './useHomeSummary';

import { AGENT_ORDER } from '../me/agentOrder';
import { NeedsAttention } from '../me/NeedsAttention';

type RingKey = 'ready' | 'hrv' | 'steps' | 'mood';

const RING_HINTS: Record<RingKey, { title: string; body: string }> = {
  ready: {
    title: 'Readiness',
    body: 'Recovery score 0–100. Combines HRV trend, sleep quality, and recent training load from Garmin.',
  },
  hrv: {
    title: 'Heart Rate Variability',
    body: 'Most recent sleep HRV normalized vs your 30-day min/max from HealthKit. Higher = more recovered nervous system.',
  },
  steps: {
    title: 'Steps',
    body: "Today's step count as % of 10 000 goal. Read live from HealthKit.",
  },
  mood: {
    title: 'Mood',
    body: "Today's mood score 0–100, logged via the mood agent.",
  },
};

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

  const isNeedsSetup = row?.status === 'needs_setup' && row.cta != null;
  const ctaKind = row?.cta?.kind;
  // Table of CTA-pill presentation. `connect`/`upload` intentionally share the
  // `info` colour family — both signal "user must wire up an external thing".
  const pill =
    ctaKind === 'integrations'
      ? { label: 'connect', fg: colors.info, bg: colors.infoSoft }
      : ctaKind === 'chat-prefill'
        ? { label: 'log', fg: colors.accent, bg: colors.accentSoft }
        : ctaKind === 'finance-upload'
          ? { label: 'upload', fg: colors.info, bg: colors.infoSoft }
          : null;

  const displayHint = row?.hint ?? hint;
  const hintColor = isNeedsSetup ? colors.fg2 : colors.fg3;
  const valueText = isNeedsSetup ? '—' : value;
  const valueColor = isNeedsSetup ? colors.fg3 : colors.fg1;

  return (
    <Pressable
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
            {AGENT_COPY[id].label}
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

function BriefingStrip({
  text,
  open,
  onToggle,
}: {
  text: string;
  open: boolean;
  onToggle: () => void;
}) {
  const { colors, radius, typography } = useTheme();
  if (!text) return null;
  return (
    <Pressable
      onPress={onToggle}
      style={{
        backgroundColor: open ? colors.bg2 : 'transparent',
        borderWidth: 1,
        borderColor: open ? colors.border : colors.borderSoft,
        borderRadius: radius.rMd,
        padding: open ? 14 : 10,
        flexDirection: 'row',
        alignItems: open ? 'flex-start' : 'center',
        gap: 10,
      }}
    >
      <View
        style={{
          width: 22,
          height: 22,
          borderRadius: 11,
          backgroundColor: colors.accent,
          alignItems: 'center',
          justifyContent: 'center',
          marginTop: open ? 1 : 0,
        }}
      >
        <Icon name="Sparkle" size={12} color={colors.accentInk} weight="fill" />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text
          style={[
            typography.micro,
            {
              color: colors.accent,
              fontWeight: '700',
              marginBottom: open ? 6 : 0,
            },
          ]}
        >
          Morning briefing
        </Text>
        {open ? (
          <Text style={{ fontSize: 14, color: colors.fg1, lineHeight: 21 }}>{text}</Text>
        ) : (
          <Text numberOfLines={1} style={{ fontSize: 12.5, color: colors.fg2, lineHeight: 17 }}>
            {text}
          </Text>
        )}
      </View>
      <Icon name={open ? 'CaretDown' : 'CaretRight'} size={14} color={colors.fg4} />
    </Pressable>
  );
}

export function HomeScreen() {
  const { colors, typography } = useTheme();
  const t = useT(appLocale());
  const { data, isLoading, isError, refetch, isRefreshing, onRefresh } = useHomeSummary();
  const { session } = useSession();
  const [now, setNow] = useState(() => new Date());
  const [briefOpen, setBriefOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Non-null when a tile links straight into a settings sub-panel.
  const [settingsPanel, setSettingsPanel] = useState<'integrations' | null>(null);
  const [ringHint, setRingHint] = useState<RingKey | null>(null);
  const [openAgent, setOpenAgent] = useState<AgentId | null>(null);

  const router = useRouter();
  const inbox = useInbox();
  const unreadBadge = badgeText(inbox.data?.unread_count ?? 0);
  const { rows: agentRows } = useAgentStatusRows();
  const [activeIntegration, setActiveIntegration] = useState<IntegrationId | null>(null);

  useEffect(() => {
    const refreshNow = () => setNow(new Date());
    const timer = setInterval(refreshNow, 60_000);
    const subscription = AppState.addEventListener('change', (state) => {
      if (state === 'active') refreshNow();
    });

    return () => {
      clearInterval(timer);
      subscription.remove();
    };
  }, []);

  const rowsByAgent = useMemo(() => {
    const m = new Map<AgentId, AgentRow>();
    for (const r of agentRows) m.set(r.id, r);
    return m;
  }, [agentRows]);

  // Sort buckets: ready → no_data (stale) → needs log → needs connect.
  // Within each bucket we keep AGENT_ORDER as the tiebreaker so the grid is stable.
  const sortedAgentIds = useMemo(() => {
    const bucket = (id: AgentId): number => {
      const row = rowsByAgent.get(id);
      if (!row) return 1; // no row yet → treat as stale (between ready and CTA)
      if (row.status === 'ready') return 0;
      if (row.status === 'no_data') return 1;
      const kind = row.cta?.kind;
      if (kind === 'chat-prefill') return 2;
      return 3; // integrations / finance-upload
    };
    return [...AGENT_ORDER]
      .map((id, i) => ({ id, i, b: bucket(id) }))
      .sort((a, b) => a.b - b.b || a.i - b.i)
      .map((x) => x.id);
  }, [rowsByAgent]);

  if (isLoading)
    return (
      <Screen>
        <ScreenState kind="loading" skeletonCount={4} />
      </Screen>
    );
  if (isError)
    return (
      <Screen>
        <ScreenState
          kind="error"
          title="Couldn't load dashboard"
          cta={{ label: 'Retry', onPress: () => refetch() }}
        />
      </Screen>
    );

  const agentMap = new Map<AgentId, HomeAgent>((data?.agents ?? []).map((a) => [a.agent, a]));

  const displayName = session?.user?.user_metadata?.full_name as string | undefined;
  const firstName = displayName?.split(' ')[0] ?? 'there';
  const greeting = (() => {
    const h = now.getHours();
    if (h < 5) return 'Good night';
    if (h < 12) return 'Good morning';
    if (h < 17) return 'Good afternoon';
    return 'Good evening';
  })();
  const dateLabel = now
    .toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' })
    .replace(',', ' ·');

  const rings = data?.rings;
  const briefing = data?.briefingText?.trim() ?? '';

  function pushAgent(id: AgentId) {
    const row = rowsByAgent.get(id);
    if (!row) {
      setOpenAgent(id);
      return;
    }
    dispatchTilePress(row, {
      router,
      // Narrow setState dispatchers to the `(value) => void` shape the helper expects;
      // raw `Dispatch<SetStateAction<T>>` is wider in its param type and won't assign.
      openIntegration: (panel: IntegrationId) => setActiveIntegration(panel),
      openDetail: (detailId: AgentId) => setOpenAgent(detailId),
      openIntegrationsList: () => setSettingsPanel('integrations'),
    });
  }

  return (
    <Screen edges={['top']}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        refreshControl={
          <RefreshControl
            refreshing={isRefreshing}
            onRefresh={onRefresh}
            tintColor={colors.accent}
          />
        }
      >
        {/* Header */}
        <View style={styles.header}>
          <View style={{ flex: 1, minWidth: 0, marginRight: 12 }}>
            <Text
              style={{
                fontSize: 11,
                color: colors.fg3,
                fontWeight: '600',
                letterSpacing: 0.5,
                textTransform: 'uppercase',
              }}
            >
              {dateLabel}
            </Text>
            <Text
              numberOfLines={2}
              style={{
                fontFamily: typography.title1.fontFamily,
                fontSize: 26,
                color: colors.fg1,
                fontWeight: '600',
                letterSpacing: -0.7,
                marginTop: 2,
              }}
            >
              {greeting}, {firstName}
            </Text>
          </View>
          <Pressable
            testID="inbox-bell"
            accessibilityRole="button"
            accessibilityLabel={t('inbox.title')}
            onPress={() => router.push('/inbox')}
            style={[
              styles.settingsBtn,
              { backgroundColor: colors.bg2, borderColor: colors.border, marginRight: 8 },
            ]}
          >
            <Icon name="Bell" size={17} color={colors.fg2} />
            {unreadBadge && (
              <View
                style={{
                  position: 'absolute',
                  top: -4,
                  right: -4,
                  minWidth: 16,
                  height: 16,
                  borderRadius: 8,
                  backgroundColor: colors.danger,
                  alignItems: 'center',
                  justifyContent: 'center',
                  paddingHorizontal: 3,
                }}
              >
                <Text style={{ color: colors.accentInk, fontSize: 10, fontWeight: '700' }}>
                  {unreadBadge}
                </Text>
              </View>
            )}
          </Pressable>
          <Pressable
            onPress={() => setSettingsOpen(true)}
            style={[
              styles.settingsBtn,
              { backgroundColor: colors.bg2, borderColor: colors.border },
            ]}
          >
            <Icon name="Gear" size={17} color={colors.fg2} />
          </Pressable>
        </View>

        {/* Briefing strip */}
        {briefing ? (
          <BriefingStrip
            text={briefing}
            open={briefOpen}
            onToggle={() => setBriefOpen((v) => !v)}
          />
        ) : null}

        {/* Today rings */}
        <View>
          <Text
            style={[
              typography.micro,
              { color: colors.fg3, paddingHorizontal: 2, paddingBottom: 10 },
            ]}
          >
            Today
          </Text>
          <View style={styles.ringsRow}>
            <Pressable
              onPress={() => setRingHint((h) => (h === 'ready' ? null : 'ready'))}
              hitSlop={6}
            >
              <MiniRing
                pct={rings?.readyPct ?? 0}
                color={agentSolid('recovery')}
                value={rings?.readyPct != null ? `${rings.readyPct}%` : '—'}
                label="Ready"
              />
            </Pressable>
            <Pressable onPress={() => setRingHint((h) => (h === 'hrv' ? null : 'hrv'))} hitSlop={6}>
              <MiniRing
                pct={rings?.hrvPct ?? 0}
                color={agentSolid('sleep')}
                value={
                  rings?.hrvMs != null
                    ? `${rings.hrvMs}`
                    : rings?.hrvPct != null
                      ? `${rings.hrvPct}%`
                      : '—'
                }
                label="HRV"
              />
            </Pressable>
            <Pressable
              onPress={() => setRingHint((h) => (h === 'steps' ? null : 'steps'))}
              hitSlop={6}
            >
              <MiniRing
                pct={rings?.stepsPct ?? 0}
                color={agentSolid('workout')}
                value={rings?.stepsPct != null ? `${rings.stepsPct}%` : '—'}
                label="Steps"
              />
            </Pressable>
            <Pressable
              onPress={() => setRingHint((h) => (h === 'mood' ? null : 'mood'))}
              hitSlop={6}
            >
              <MiniRing
                pct={rings?.moodPct ?? 0}
                color={agentSolid('mood')}
                value={rings?.moodPct != null ? `${rings.moodPct}%` : '—'}
                label="Mood"
              />
            </Pressable>
          </View>
          {ringHint && (
            <Pressable
              onPress={() => setRingHint(null)}
              style={[
                styles.ringHintCard,
                { backgroundColor: colors.bg2, borderColor: colors.borderSoft },
              ]}
            >
              <Text style={{ fontSize: 12, fontWeight: '600', color: colors.fg1 }}>
                {RING_HINTS[ringHint].title}
              </Text>
              <Text style={{ fontSize: 12, color: colors.fg2, marginTop: 2, lineHeight: 17 }}>
                {RING_HINTS[ringHint].body}
              </Text>
            </Pressable>
          )}
        </View>

        {/* Needs attention */}
        <NeedsAttention
          alerts={data?.alerts ?? []}
          open={alertsOpen}
          onToggle={() => setAlertsOpen((v) => !v)}
        />

        {/* Agents grid */}
        <View>
          <View style={styles.sectionHeader}>
            <Text style={[typography.micro, { color: colors.fg3 }]}>Agents</Text>
            <Text
              style={{
                fontFamily: typography.mono.fontFamily,
                fontSize: 10.5,
                color: colors.fg4,
              }}
            >
              {AGENT_ORDER.length}
            </Text>
          </View>
          <View style={styles.grid}>
            {sortedAgentIds
              .filter((id) => !data?.unavailable?.includes(id))
              .map((id) => {
                const row = rowsByAgent.get(id);
                const agent = agentMap.get(id);
                return (
                  <View key={id} style={styles.gridCell}>
                    <AgentTile
                      id={id}
                      value={agent?.metric ?? '—'}
                      hint={agent?.detail ?? ''}
                      row={row}
                      onPress={pushAgent}
                    />
                  </View>
                );
              })}
          </View>
          <UnavailableNote agents={data?.unavailable ?? []} />
        </View>
      </ScrollView>

      <SettingsSheet
        visible={settingsOpen || settingsPanel !== null}
        initialPanel={settingsPanel ?? undefined}
        onClose={() => {
          setSettingsOpen(false);
          setSettingsPanel(null);
        }}
      />
      <AgentDetailSheet
        visible={openAgent !== null}
        agentId={openAgent}
        onClose={() => setOpenAgent(null)}
      />
      <IntegrationSheet
        integration={activeIntegration}
        onClose={() => setActiveIntegration(null)}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  scroll: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 24, gap: 18 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-end',
    paddingHorizontal: 2,
    paddingTop: 8,
  },
  settingsBtn: {
    width: 38,
    height: 38,
    borderRadius: 19,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ringsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
  },
  ringHintCard: {
    marginTop: 12,
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    paddingHorizontal: 2,
    paddingBottom: 10,
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginHorizontal: -4,
  },
  gridCell: {
    width: '50%',
    paddingHorizontal: 4,
    paddingBottom: 8,
  },
  tile: {
    borderWidth: 1,
    minHeight: 76,
    paddingVertical: 12,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  tileLabelRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    gap: 8,
  },
});
