import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AppState, RefreshControl, ScrollView, Text } from 'react-native';
import { Screen, useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { errorCode } from '@/api/gateway';
import { appLocale } from '@/lib/locale';
import { openTask } from '../task/sheetStore';
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
import { BodyProfileSheet } from '../home/BodyProfileSheet';
import { DayFeed } from './DayFeed';
import { DaySwitcher } from './DaySwitcher';
import { AttentionList } from './AttentionList';
import { useAttention, useDismissAttention, type AttentionItem } from './useAttention';
import { MeHeader } from './MeHeader';
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
  const t = useT(appLocale());
  const isToday = offset === 0;
  const attention = useAttention(isToday);
  const dismiss = useDismissAttention();
  const [notice, setNotice] = useState<string | null>(null);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), 3000);
    return () => clearTimeout(timer);
  }, [notice]);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsPanel, setSettingsPanel] = useState<'integrations' | null>(null);
  const [activeIntegration, setActiveIntegration] = useState<IntegrationId | null>(null);
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
  const { refetch: refetchAttention } = attention;
  useFocusEffect(
    useCallback(() => {
      void refetchSummary();
      void refetchFeed();
      void refetchAttention();
    }, [refetchSummary, refetchFeed, refetchAttention]),
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

  const openAttention = useCallback(
    (item: AttentionItem) => {
      const agent = item.agent as AgentId;
      if (item.action.type === 'profile') setProfileOpen(true);
      else if (item.action.type === 'task')
        openTask({ lead: agent, prefill: item.action.prompt ?? '' });
      else showAgent(agent);
    },
    [showAgent],
  );
  const { mutate: dismissMutate } = dismiss;
  const hide = useCallback(
    (id: string) =>
      dismissMutate(id, {
        onError: (error) => {
          if (errorCode(error) !== 'not_dismissable') setNotice(t('attention.hide_failed'));
        },
      }),
    [dismissMutate, t],
  );
  const attentionUnavailable = isToday ? attention.data?.unavailable : undefined;

  const refreshing = summary.isRefreshing || feed.isRefetching;
  const onRefresh = useCallback(() => {
    void summary.onRefresh();
    void feed.refetch();
    void attention.refetch();
  }, [summary, feed, attention]);
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
          onAgents={() => setPager('all')}
        />
        <DaySwitcher offset={offset} today={now} onChange={setOffset} />
        {isToday && (
          <AttentionList
            items={attention.data?.items ?? []}
            onOpen={openAttention}
            onDismiss={hide}
          />
        )}
        <DayFeed
          extraUnavailable={attentionUnavailable}
          feed={feed.data}
          loading={feed.isLoading}
          error={feed.isError}
          onRetry={() => void feed.refetch()}
          onOpenAgent={showAgent}
        />
      </ScrollView>
      {notice && (
        <Text
          style={{
            position: 'absolute',
            bottom: 100,
            alignSelf: 'center',
            backgroundColor: colors.bg3,
            color: colors.fg1,
            paddingHorizontal: 14,
            paddingVertical: 8,
            borderRadius: 16,
            overflow: 'hidden',
          }}
        >
          {notice}
        </Text>
      )}
      <BodyProfileSheet
        visible={profileOpen}
        onClose={() => setProfileOpen(false)}
        onSaved={() => {
          void summary.refetch();
          void attention.refetch();
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
