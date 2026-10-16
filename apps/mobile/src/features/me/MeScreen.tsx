import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AppState, RefreshControl, ScrollView } from 'react-native';
import { Screen, useTheme, type AgentId } from '@life-agents/ui';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useHomeSummary } from '../home/useHomeSummary';
import { useSession } from '../auth/useSession';
import { useInbox } from '../inbox/useInbox';
import { badgeText } from '../inbox/badge';
import { useAgentStatusRows } from '../agents/useAgentStatusRows';
import { dispatchTilePress } from '../agents/agentTileDispatch';
import { SettingsSheet } from '../more/SettingsSheet';
import { AgentPagerSheet, PAGES, type PagerStart } from './AgentPagerSheet';
import { StandaloneAgentSheet } from './StandaloneAgentSheet';
import { DETAIL_AGENTS } from './agentOrder';
import { IntegrationSheet } from '../integrations/IntegrationSheet';
import type { IntegrationId } from '../integrations/store';
import { BodyProfileAlert } from '../home/BodyProfileAlert';
import { BodyProfileSheet } from '../home/BodyProfileSheet';
import { DayFeed } from './DayFeed';
import { DaySwitcher } from './DaySwitcher';
import { MetricChips } from './MetricChips';
import { MeHeader } from './MeHeader';
import { NeedsAttention } from './NeedsAttention';
import { feedDay, useDayFeed } from './useDayFeed';
export function MeScreen() {
  const { colors } = useTheme();
  const router = useRouter();
  const summary = useHomeSummary();
  const { session } = useSession();
  const inbox = useInbox();
  const { rows } = useAgentStatusRows();
  const [now, setNow] = useState(() => new Date());
  const [offset, setOffset] = useState(0);
  const day = feedDay(now, offset);
  const feed = useDayFeed(day);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsPanel, setSettingsPanel] = useState<'integrations' | null>(null);
  const [activeIntegration, setActiveIntegration] = useState<IntegrationId | null>(null);
  const [alertsOpen, setAlertsOpen] = useState(false);
  const [pager, setPager] = useState<PagerStart | null>(null);
  const params = useLocalSearchParams<{ agent?: string }>();
  useEffect(() => {
    const id = params.agent;
    if (id && PAGES.includes(id as PagerStart)) {
      setPager(id as PagerStart);
      router.setParams({ agent: undefined });
    }
  }, [params.agent, router]);

  const [standalone, setStandalone] = useState<'body' | 'home' | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);
  const { refetch: refetchSummary } = summary;
  const { refetch: refetchFeed } = feed;
  useFocusEffect(
    useCallback(() => {
      void refetchSummary();
      void refetchFeed();
    }, [refetchSummary, refetchFeed]),
  );
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

  const rowsByAgent = useMemo(() => new Map(rows.map((r) => [r.id, r])), [rows]);
  const showAgent = useCallback(
    (id: AgentId) => {
      const row = rowsByAgent.get(id);
      if (DETAIL_AGENTS.has(id) && row?.status !== 'needs_setup') {
        setPager(id);
        return;
      }
      if (!row) return;
      dispatchTilePress(row, {
        router,
        openIntegration: (panel: IntegrationId) => setActiveIntegration(panel),
        openDetail: (detailId: AgentId) => {
          if (detailId === 'body' || detailId === 'home') setStandalone(detailId);
          else setPager(detailId);
        },
        openIntegrationsList: () => setSettingsPanel('integrations'),
      });
    },
    [rowsByAgent, router],
  );

  const refreshing = summary.isRefreshing || feed.isRefetching;
  const onRefresh = useCallback(() => {
    void summary.onRefresh();
    void feed.refetch();
  }, [summary, feed]);
  const firstName =
    (session?.user?.user_metadata?.full_name as string | undefined)?.split(' ')[0] ?? '';

  return (
    <Screen edges={['top']}>
      <ScrollView
        contentContainerStyle={{
          paddingHorizontal: 16,
          paddingTop: 8,
          paddingBottom: 120,
          gap: 16,
        }}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.accent} />
        }
      >
        <MeHeader
          now={now}
          firstName={firstName}
          unreadBadge={badgeText(inbox.data?.unread_count ?? 0)}
          onInbox={() => router.push('/inbox')}
          onSettings={() => setSettingsOpen(true)}
        />
        {summary.data && (
          <MetricChips
            summary={summary.data}
            rows={rowsByAgent}
            onAgent={showAgent}
            onAll={() => setPager('all')}
          />
        )}
        <NeedsAttention
          alerts={summary.data?.alerts ?? []}
          open={alertsOpen}
          onToggle={() => setAlertsOpen((v) => !v)}
        />
        {summary.data?.agents.some((a) => a.agent === 'nutrition' && a.progress === null) && (
          <BodyProfileAlert onPress={() => setProfileOpen(true)} />
        )}
        <DaySwitcher offset={offset} today={now} onChange={setOffset} />
        <DayFeed
          feed={feed.data}
          loading={feed.isLoading}
          error={feed.isError}
          onRetry={() => void feed.refetch()}
          onOpenAgent={showAgent}
        />
      </ScrollView>
      <BodyProfileSheet
        visible={profileOpen}
        onClose={() => setProfileOpen(false)}
        onSaved={() => {
          void summary.refetch();
        }}
      />
      <SettingsSheet
        visible={settingsOpen || settingsPanel !== null}
        initialPanel={settingsPanel ?? undefined}
        onClose={() => {
          setSettingsOpen(false);
          setSettingsPanel(null);
        }}
      />
      <StandaloneAgentSheet agent={standalone} onClose={() => setStandalone(null)} />
      <AgentPagerSheet
        start={pager}
        summary={summary.data}
        rows={rowsByAgent}
        onPickOther={showAgent}
        onClose={() => setPager(null)}
      />
      <IntegrationSheet
        integration={activeIntegration}
        onClose={() => setActiveIntegration(null)}
      />
    </Screen>
  );
}
