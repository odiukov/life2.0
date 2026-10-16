import React, { useEffect, useRef, useState } from 'react';
import {
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from 'react-native';
import Animated from 'react-native-reanimated';
import { Gesture, GestureDetector, GestureHandlerRootView } from 'react-native-gesture-handler';
import { Icon, useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { useSheetAnimation } from '@/lib/sheetAnimation';
import { useSwipeToDismiss } from '@/lib/useSwipeToDismiss';
import { KitchenPanel } from '../kitchen/KitchenScreen';
import { AgentDetailContent } from '../home/AgentDetailContent';
import type { HomeSummary } from '../home/useHomeSummary';
import type { AgentRow } from '../agents/agentStatusRules';
import { openTask } from '../task/sheetStore';
import { AGENT_ORDER, DETAIL_AGENTS } from './agentOrder';
import { AllAgentsGrid } from './AllAgentsGrid';

const BACKDROP_COLOR = 'rgba(0,0,0,0.6)';

export type PagerStart = AgentId | 'all';
export const PAGES: readonly PagerStart[] = [
  'all',
  ...AGENT_ORDER.filter((a) => DETAIL_AGENTS.has(a)),
];
type Props = {
  start: PagerStart | null;
  onClose: () => void;
  onPickOther: (id: AgentId) => void;
  summary?: HomeSummary;
  rows?: ReadonlyMap<AgentId, AgentRow>;
};

// Each page owns its scroll/dismiss state, including when revisiting a scrolled page.
function PagerPage({
  active,
  children,
  sheetY,
  backdropAlpha,
  onClose,
}: {
  active: boolean;
  children: React.ReactNode;
  sheetY: ReturnType<typeof useSheetAnimation>['sheetY'];
  backdropAlpha: ReturnType<typeof useSheetAnimation>['backdropAlpha'];
  onClose: () => void;
}) {
  const { panGesture, scrollHandler } = useSwipeToDismiss({
    sheetY,
    backdropAlpha,
    onClose,
    enabled: active,
  });
  return (
    <GestureDetector gesture={Gesture.Simultaneous(panGesture, Gesture.Native())}>
      <Animated.ScrollView
        onScroll={scrollHandler}
        scrollEventThrottle={16}
        contentContainerStyle={styles.content}
      >
        {children}
      </Animated.ScrollView>
    </GestureDetector>
  );
}
export function AgentPagerSheet({ start, onClose, onPickOther, summary, rows }: Props) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  const { width } = useWindowDimensions();
  const visible = start !== null;
  const animation = useSheetAnimation(visible);
  const { mounted, sheetY, backdropAlpha, backdropStyle, sheetStyle } = animation;
  const list = useRef<FlatList<PagerStart>>(null);
  const [index, setIndex] = useState(() => Math.max(0, PAGES.indexOf(start ?? 'all')));
  const target = Math.max(0, PAGES.indexOf(start ?? 'all'));
  const position = useRef({ index, width });
  position.current = { index, width };
  const syncPosition = () => {
    if (visible) list.current?.scrollToOffset({ offset: index * width, animated: false });
  };
  useEffect(() => {
    if (!visible) return;
    position.current.index = target;
    setIndex(target);
    list.current?.scrollToOffset({ offset: target * position.current.width, animated: false });
  }, [visible, target]);
  useEffect(() => {
    if (!visible || !mounted) return;
    list.current?.scrollToOffset({ offset: position.current.index * width, animated: false });
  }, [visible, width, mounted]);
  const goTo = (i: number) => {
    const next = Math.max(0, Math.min(PAGES.length - 1, i));
    list.current?.scrollToOffset({ offset: next * width, animated: true });
    setIndex(next);
  };
  const pick = (id: AgentId) => {
    const i = PAGES.indexOf(id);
    if (i >= 0 && rows?.get(id)?.status !== 'needs_setup') goTo(i);
    else {
      onClose();
      onPickOther(id);
    }
  };
  if (!mounted) return null;
  const page = PAGES[index] ?? 'all';
  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <GestureHandlerRootView style={styles.root}>
        <View style={styles.overlay}>
          <Animated.View pointerEvents="none" style={[styles.backdrop, backdropStyle]} />
          <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
          <Animated.View style={[styles.sheet, { backgroundColor: colors.bg1 }, sheetStyle]}>
            <View style={[styles.handle, { backgroundColor: colors.bg3 }]} />
            <View style={styles.header}>
              <Pressable
                accessibilityLabel={t('me.prev_agent')}
                disabled={index === 0}
                onPress={() => goTo(index - 1)}
                hitSlop={10}
              >
                <Icon name="CaretLeft" size={18} color={colors.fg2} />
              </Pressable>
              <Text style={[styles.title, { color: colors.fg1 }]}>
                {page === 'all'
                  ? t('me.all_agents')
                  : `${t(`dashboard.agent_labels.${page}`)}  ${index}/${PAGES.length - 1}`}
              </Text>
              <Pressable
                accessibilityLabel={t('me.next_agent')}
                disabled={index === PAGES.length - 1}
                onPress={() => goTo(index + 1)}
                hitSlop={10}
              >
                <Icon name="CaretRight" size={18} color={colors.fg2} />
              </Pressable>
            </View>
            <FlatList
              ref={list}
              testID="agent-pager"
              data={PAGES}
              horizontal
              pagingEnabled
              showsHorizontalScrollIndicator={false}
              onLayout={syncPosition}
              initialScrollIndex={target}
              getItemLayout={(_d, i) => ({ length: width, offset: width * i, index: i })}
              initialNumToRender={PAGES.length}
              windowSize={PAGES.length}
              keyExtractor={(p) => p}
              onMomentumScrollEnd={(e) =>
                setIndex(
                  Math.max(
                    0,
                    Math.min(PAGES.length - 1, Math.round(e.nativeEvent.contentOffset.x / width)),
                  ),
                )
              }
              renderItem={({ item, index: i }) => (
                <View style={{ width }}>
                  <PagerPage
                    active={visible && i === index}
                    sheetY={sheetY}
                    backdropAlpha={backdropAlpha}
                    onClose={onClose}
                  >
                    {item === 'all' ? (
                      <AllAgentsGrid summary={summary} rows={rows} onPick={pick} />
                    ) : item === 'kitchen' ? (
                      <KitchenPanel />
                    ) : (
                      <AgentDetailContent
                        agentId={item}
                        enabled={visible && i === index}
                        onAction={(message) => {
                          onClose();
                          setTimeout(() => openTask({ lead: item, send: message }), 150);
                        }}
                      />
                    )}
                  </PagerPage>
                </View>
              )}
            />
          </Animated.View>
        </View>
      </GestureHandlerRootView>
    </Modal>
  );
}
const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: BACKDROP_COLOR },
  content: { padding: 16, paddingBottom: 48 },
  handle: { alignSelf: 'center', borderRadius: 2, height: 4, marginTop: 8, width: 36 },
  header: {
    alignItems: 'center',
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  overlay: { flex: 1, justifyContent: 'flex-end' },
  root: { flex: 1 },
  sheet: { borderTopLeftRadius: 22, borderTopRightRadius: 22, height: '88%', overflow: 'hidden' },
  title: { flex: 1, fontWeight: '600', textAlign: 'center' },
});
