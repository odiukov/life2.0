import React, { useEffect, useState } from 'react';
import {
  Alert,
  Dimensions,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Animated, {
  Easing,
  Extrapolation,
  interpolate,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { Gesture, GestureDetector, GestureHandlerRootView } from 'react-native-gesture-handler';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Card, Icon, useTheme, agentSolid } from '@life-agents/ui';
import { useSession } from '@/features/auth/useSession';
import { SUPABASE_CONFIGURED } from '@/features/auth/SupabaseClient';
import {
  BACKDROP_IN_MS,
  BACKDROP_OUT_MS,
  EXIT_MS,
  SHEET_SPRING,
  useSheetAnimation,
} from '@/lib/sheetAnimation';
import { useSwipeToDismiss } from '@/lib/useSwipeToDismiss';
import { AppleHealthPanel } from '@/features/integrations/panels/AppleHealthPanel';
import { GarminPanel } from '@/features/integrations/panels/GarminPanel';
import { GoogleCalendarPanel } from '@/features/integrations/panels/GoogleCalendarPanel';
import { HaPanel } from '@/features/integrations/panels/HaPanel';
import { YazioPanel } from '@/features/integrations/panels/YazioPanel';
import {
  hydrateIntegrationsFromSecureStore,
  isConnected,
  useIntegrationsStore,
} from '@/features/integrations/store';
import { SubscriptionContent } from '@/features/subscription/SubscriptionScreen';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');

// ─── Types ────────────────────────────────────────────────────────────────────

type IntegrationId = 'apple-health' | 'garmin' | 'yazio' | 'google-calendar' | 'ha';
type SubPanel =
  | 'integrations'
  | `integration-${IntegrationId}`
  | 'privacy'
  | 'subscription'
  | 'about';

// ─── Integration list data ────────────────────────────────────────────────────

// `storeId` maps to the Zustand store's IntegrationId domain ('calendar' there
// vs. 'google-calendar' in this sheet's local routing keys).
const INTEGRATIONS = [
  {
    id: 'apple-health' as IntegrationId,
    storeId: 'apple-health' as const,
    label: 'Apple Health',
    brand: 'HK',
    desc: 'Sleep, HRV, workouts, steps',
    agent: 'sleep',
  },
  {
    id: 'ha' as IntegrationId,
    storeId: 'ha' as const,
    label: 'Home Assistant',
    brand: 'HA',
    desc: 'Connect your smart home hub',
    agent: 'home',
  },
  {
    id: 'yazio' as IntegrationId,
    storeId: 'yazio' as const,
    label: 'Yazio',
    brand: 'YZ',
    desc: 'Nutrition and food tracking',
    agent: 'nutrition',
  },
  {
    id: 'garmin' as IntegrationId,
    storeId: 'garmin' as const,
    label: 'Garmin Connect',
    brand: 'GC',
    desc: 'Workouts, sleep and HRV',
    agent: 'workout',
  },
  {
    id: 'google-calendar' as IntegrationId,
    storeId: 'calendar' as const,
    label: 'Google Calendar',
    brand: 'GC',
    desc: 'Sync calendar events',
    agent: 'calendar',
  },
] as const;

const COMING_SOON = [
  { label: 'Payoneer', brand: 'PY', desc: 'Income & spending feed — coming soon' },
];

// ─── Sub-panel content components ────────────────────────────────────────────

function IntegrationsContent({ onSelect }: { onSelect: (id: IntegrationId) => void }) {
  const { colors, spacing, typography } = useTheme();
  // Subscribe directly so connect/disconnect inside a child sub-panel updates
  // the row badges without needing this component to re-mount.
  const status = useIntegrationsStore((s) => s.status);

  return (
    <ScrollView
      showsVerticalScrollIndicator={false}
      contentContainerStyle={{ padding: spacing.s4, gap: spacing.s3, paddingBottom: 32 }}
    >
      <Text style={[typography.display, { color: colors.fg1 }]}>Integrations</Text>
      <Text style={[typography.body, { color: colors.fg3, marginTop: -spacing.s2 }]}>
        Connect a source and the right agent will start referencing it.
      </Text>

      <View style={{ gap: spacing.s2 }}>
        {INTEGRATIONS.map((it) => {
          const connected = isConnected(status[it.storeId]);
          const chipColor = connected ? agentSolid(it.agent as any) : colors.fg3;
          const chipBg = connected ? agentSolid(it.agent as any) + '22' : colors.bg3;
          return (
            <Pressable key={it.id} onPress={() => onSelect(it.id)}>
              <Card>
                <View style={s.row}>
                  <View
                    style={[s.brandChip, { backgroundColor: chipBg, borderColor: colors.border }]}
                  >
                    <Text style={{ color: chipColor, fontSize: 11, fontWeight: '700' }}>
                      {it.brand}
                    </Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                      <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{it.label}</Text>
                      {connected && (
                        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                          <View style={[s.connDot, { backgroundColor: colors.success }]} />
                          <Text
                            style={{ fontSize: 10.5, color: colors.success, fontWeight: '600' }}
                          >
                            Connected
                          </Text>
                        </View>
                      )}
                    </View>
                    <Text style={[typography.caption, { color: colors.fg3, marginTop: 2 }]}>
                      {it.desc}
                    </Text>
                  </View>
                  <Text style={{ color: colors.fg4, fontSize: 16 }}>›</Text>
                </View>
              </Card>
            </Pressable>
          );
        })}

        {COMING_SOON.map((it) => (
          <Card key={it.label}>
            <View style={s.row}>
              <View
                style={[s.brandChip, { backgroundColor: colors.bg3, borderColor: colors.border }]}
              >
                <Text style={{ color: colors.fg3, fontSize: 11, fontWeight: '700' }}>
                  {it.brand}
                </Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[typography.bodyEm, { color: colors.fg3 }]}>{it.label}</Text>
                <Text style={[typography.caption, { color: colors.fg3, marginTop: 2 }]}>
                  {it.desc}
                </Text>
              </View>
            </View>
          </Card>
        ))}
      </View>

      <View style={[s.privacyNote, { borderColor: colors.border }]}>
        <Text style={[typography.caption, { color: colors.fg3, lineHeight: 18 }]}>
          All tokens are stored in the device secure enclave. Nothing leaves your phone unless an
          agent needs it.
        </Text>
      </View>
    </ScrollView>
  );
}

function PlaceholderContent({ title }: { title: string }) {
  const { colors, spacing, typography } = useTheme();
  return (
    <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.s4 }}>
      <Text style={[typography.title1, { color: colors.fg1, marginBottom: spacing.s2 }]}>
        {title}
      </Text>
      <Text style={[typography.body, { color: colors.fg3, textAlign: 'center' }]}>Coming soon</Text>
    </View>
  );
}

// ─── Main component ───────────────────────────────────────────────────────────

const NAV_ROWS = [
  { key: 'integrations', label: 'Integrations', hint: 'Connected sources', icon: 'Plugs' },
  { key: 'privacy', label: 'Privacy & data', hint: 'On-device by default', icon: 'ShieldCheck' },
  {
    key: 'subscription',
    label: 'Subscription & Tokens',
    hint: 'Life+ · monthly',
    icon: 'CreditCard',
  },
  { key: 'about', label: 'About Life Agents', hint: 'v0.0.1', icon: 'Info' },
] as const;

type Props = {
  visible: boolean;
  onClose: () => void;
  /** Sub-panel to open straight away, e.g. when a home tile links into settings. */
  initialPanel?: SubPanel;
};

export function SettingsSheet({ visible, onClose, initialPanel }: Props) {
  const { colors, spacing, typography } = useTheme();
  const { session, signOut } = useSession();
  const insets = useSafeAreaInsets();

  // Main sheet
  const { mounted, sheetY, backdropAlpha, backdropStyle } = useSheetAnimation(visible);
  const { panGesture: rootPanGesture, scrollHandler: rootScrollHandler } = useSwipeToDismiss({
    sheetY,
    backdropAlpha,
    onClose,
  });

  // Sub-panel stack
  const [panelStack, setPanelStack] = useState<SubPanel[]>([]);
  const subY = useSharedValue(SCREEN_HEIGHT);
  const subAlpha = useSharedValue(0);
  const topY = useSharedValue(SCREEN_HEIGHT);
  // mainPush: 0 = no sub-panels, 1 = first sub-panel open, 2 = second, ...
  // bgPush:   0 = bg-sheet at rest, 1 = bg-sheet pushed back by top-sheet
  const mainPush = useSharedValue(0);
  const bgPush = useSharedValue(0);

  const subMounted = panelStack.length > 0;
  const currentPanel = panelStack[panelStack.length - 1] ?? null;
  const prevPanel = panelStack[panelStack.length - 2] ?? null;

  function openSub(panel: SubPanel) {
    setPanelStack([panel]);
    topY.value = SCREEN_HEIGHT;
    bgPush.value = 0;
    mainPush.value = withSpring(1, SHEET_SPRING);
    subY.value = SCREEN_HEIGHT;
    subAlpha.value = 0;
    subAlpha.value = withTiming(1, { duration: BACKDROP_IN_MS, easing: Easing.out(Easing.quad) });
    subY.value = withSpring(0, SHEET_SPRING);
  }

  function pushSub(panel: SubPanel) {
    const newDepth = panelStack.length + 1;
    topY.value = SCREEN_HEIGHT;
    mainPush.value = withSpring(newDepth, SHEET_SPRING);
    bgPush.value = withSpring(1, SHEET_SPRING);
    setPanelStack((prev) => [...prev, panel]);
    topY.value = withSpring(0, SHEET_SPRING);
  }

  function afterPop() {
    topY.value = SCREEN_HEIGHT;
    setPanelStack((prev) => prev.slice(0, -1));
  }

  function popSub() {
    if (panelStack.length <= 1) {
      closeSub();
    } else {
      const newDepth = panelStack.length - 1;
      mainPush.value = withSpring(newDepth, SHEET_SPRING);
      bgPush.value = withSpring(newDepth >= 2 ? 1 : 0, SHEET_SPRING);
      topY.value = withTiming(
        SCREEN_HEIGHT,
        { duration: EXIT_MS, easing: Easing.in(Easing.cubic) },
        (finished) => {
          if (finished) runOnJS(afterPop)();
        },
      );
    }
  }

  function afterCloseAnim() {
    setPanelStack([]);
  }

  function closeSub() {
    mainPush.value = withSpring(0, SHEET_SPRING);
    bgPush.value = 0;
    subAlpha.value = withTiming(0, { duration: BACKDROP_OUT_MS, easing: Easing.in(Easing.quad) });
    subY.value = withTiming(
      SCREEN_HEIGHT,
      { duration: EXIT_MS, easing: Easing.in(Easing.cubic) },
      (finished) => {
        if (finished) runOnJS(afterCloseAnim)();
      },
    );
  }

  // Throwaway target for the swipe-dismiss backdrop fade when popping from depth >= 2.
  // In that case the real `subAlpha` must remain at 1 because the under-layer sub-panel
  // stays visible and needs its scrim against the main settings sheet beneath.
  const subSwipeScrimScratch = useSharedValue(1);

  const { panGesture: subPanGesture, scrollHandler: subScrollHandler } = useSwipeToDismiss({
    sheetY: panelStack.length >= 2 ? topY : subY,
    backdropAlpha: panelStack.length >= 2 ? subSwipeScrimScratch : subAlpha,
    onClose: popSub,
    enabled: subMounted,
  });
  // Compose with Gesture.Native() so the inner ScrollView in panel content
  // (IntegrationsContent, SubscriptionContent, etc.) doesn't swallow downward
  // touches before our pan can activate. activeOffsetY([10, 999]) on the pan
  // means scroll still wins for upward swipes and small motions; only a clear
  // downward drag triggers dismiss.
  const subSheetGesture = Gesture.Simultaneous(subPanGesture, Gesture.Native());

  useEffect(() => {
    if (!visible) {
      setPanelStack([]);
      subY.value = SCREEN_HEIGHT;
      subAlpha.value = 0;
      topY.value = SCREEN_HEIGHT;
      mainPush.value = 0;
      bgPush.value = 0;
    } else {
      // Background HK sync (and other out-of-tree writers) can mutate the
      // SecureStore keys while this sheet is closed. Re-hydrate on open so
      // the badges aren't stale when the sheet appears.
      hydrateIntegrationsFromSecureStore().catch(() => {});
      // Callers can link straight into a sub-panel (e.g. a home tile that
      // needs the integrations list) instead of the settings root.
      if (initialPanel) openSub(initialPanel);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, initialPanel]);

  const subSheetStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: subY.value },
      { scale: interpolate(bgPush.value, [0, 1], [1, 0.94], Extrapolation.CLAMP) },
    ],
  }));
  const subScrimStyle = useAnimatedStyle(() => ({ opacity: subAlpha.value }));
  const topSheetStyle = useAnimatedStyle(() => ({ transform: [{ translateY: topY.value }] }));
  const mainSheetStyle = useAnimatedStyle(() => ({
    transform: [
      {
        translateY:
          sheetY.value +
          interpolate(mainPush.value, [0, 1, 2, 3], [0, -14, -24, -32], Extrapolation.CLAMP),
      },
      {
        scale: interpolate(
          mainPush.value,
          [0, 1, 2, 3],
          [1, 0.93, 0.87, 0.83],
          Extrapolation.CLAMP,
        ),
      },
    ],
  }));

  if (!mounted) return null;

  const email = session?.user?.email ?? null;
  const displayName = session?.user?.user_metadata?.full_name as string | undefined;
  const initials = (displayName ?? email ?? 'U')
    .split(' ')
    .map((w: string) => w[0] ?? '')
    .join('')
    .toUpperCase()
    .slice(0, 2);

  function confirmSignOut() {
    Alert.alert('Sign out?', 'You can sign back in at any time.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign out',
        style: 'destructive',
        onPress: async () => {
          await signOut();
        },
      },
    ]);
  }

  function renderPanel(panel: SubPanel | null) {
    // Sync the Zustand store the instant a panel reports a status change so
    // the Integrations list updates without waiting for a re-mount.
    const setStoreStatus = useIntegrationsStore.getState().set;
    switch (panel) {
      case 'integrations':
        return <IntegrationsContent onSelect={(id) => pushSub(`integration-${id}`)} />;
      case 'integration-apple-health':
        return (
          <Animated.ScrollView
            onScroll={subScrollHandler}
            scrollEventThrottle={16}
            contentContainerStyle={{ paddingBottom: 32 }}
          >
            <AppleHealthPanel
              onConnected={() => setStoreStatus('apple-health', 'connected')}
              onDisconnected={() => setStoreStatus('apple-health', 'not-connected')}
            />
          </Animated.ScrollView>
        );
      case 'integration-garmin':
        return (
          <GarminPanel
            onConnected={() => setStoreStatus('garmin', 'connected')}
            onDisconnected={() => setStoreStatus('garmin', 'not-connected')}
            onScroll={subScrollHandler}
            scrollEventThrottle={16}
          />
        );
      case 'integration-yazio':
        return (
          <YazioPanel
            onConnected={() => setStoreStatus('yazio', 'connected')}
            onDisconnected={() => setStoreStatus('yazio', 'not-connected')}
            onScroll={subScrollHandler}
            scrollEventThrottle={16}
          />
        );
      case 'integration-google-calendar':
        return (
          <GoogleCalendarPanel
            onConnected={() => setStoreStatus('calendar', 'connected')}
            onDisconnected={() => setStoreStatus('calendar', 'not-connected')}
            onScroll={subScrollHandler}
            scrollEventThrottle={16}
          />
        );
      case 'integration-ha':
        return (
          <HaPanel
            onConnected={() => setStoreStatus('ha', 'connected')}
            onDisconnected={() => setStoreStatus('ha', 'not-connected')}
            onScroll={subScrollHandler}
            scrollEventThrottle={16}
          />
        );
      case 'privacy':
        return <PlaceholderContent title="Privacy & data" />;
      case 'subscription':
        // Subscription is the only long, scrollable sub-panel — wrap with a
        // fixed height so its inner ScrollView has a bounded parent.
        return (
          <View style={{ height: SCREEN_HEIGHT * 0.85 }}>
            <SubscriptionContent onScroll={subScrollHandler} scrollEventThrottle={16} />
          </View>
        );
      case 'about':
        return <PlaceholderContent title="About Life Agents" />;
      default:
        return null;
    }
  }

  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={subMounted ? popSub : onClose}
      statusBarTranslucent
    >
      <GestureHandlerRootView style={{ flex: 1 }}>
        <View style={styles.overlay}>
          {/* Main backdrop */}
          <Animated.View style={[styles.backdrop, backdropStyle]} pointerEvents="none" />
          <Pressable style={StyleSheet.absoluteFill} onPress={subMounted ? closeSub : onClose} />

          {/* Main sheet */}
          <GestureDetector gesture={rootPanGesture}>
            <Animated.View style={[styles.sheet, { backgroundColor: colors.bg2 }, mainSheetStyle]}>
              <View style={[styles.handle, { backgroundColor: colors.bg3 }]} />

              <Animated.ScrollView
                onScroll={rootScrollHandler}
                scrollEventThrottle={16}
                showsVerticalScrollIndicator={false}
                contentContainerStyle={{ paddingBottom: 32 }}
              >
                {/* Profile */}
                <View style={[styles.profileRow, { marginBottom: spacing.s4 }]}>
                  <View style={[styles.avatar, { backgroundColor: colors.accent }]}>
                    <Text style={{ color: colors.accentInk, fontWeight: '700', fontSize: 18 }}>
                      {initials}
                    </Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={[typography.bodyEm, { color: colors.fg1 }]}>
                      {displayName ?? 'Life User'}
                    </Text>
                    {email && (
                      <Text style={[typography.caption, { color: colors.fg3 }]}>{email}</Text>
                    )}
                  </View>
                  <View style={[styles.lifePlusBadge, { backgroundColor: colors.accent }]}>
                    <Text
                      style={{
                        color: colors.accentInk,
                        fontSize: 10,
                        fontWeight: '700',
                        letterSpacing: 0.5,
                      }}
                    >
                      LIFE+
                    </Text>
                  </View>
                </View>

                {/* Nav rows */}
                <Text style={[typography.micro, { color: colors.fg3, marginBottom: spacing.s2 }]}>
                  SETTINGS
                </Text>
                <Card pad={0}>
                  {NAV_ROWS.map((row, i) => (
                    <Pressable
                      key={row.key}
                      onPress={() => openSub(row.key as SubPanel)}
                      style={[
                        styles.navRow,
                        i > 0 && { borderTopWidth: 1, borderTopColor: colors.borderSoft },
                      ]}
                    >
                      <View style={[styles.iconChip, { backgroundColor: colors.bg3 }]}>
                        <Icon name={row.icon as any} size={16} color={colors.fg2} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={[typography.body, { color: colors.fg1, fontWeight: '600' }]}>
                          {row.label}
                        </Text>
                        <Text style={[typography.caption, { color: colors.fg3, marginTop: 1 }]}>
                          {row.hint}
                        </Text>
                      </View>
                      <Text style={{ color: colors.fg4, fontSize: 16 }}>›</Text>
                    </Pressable>
                  ))}
                </Card>

                {/* Sign out */}
                {SUPABASE_CONFIGURED && session && (
                  <Pressable
                    testID="sign-out"
                    onPress={confirmSignOut}
                    style={[
                      styles.signOut,
                      { backgroundColor: colors.danger, marginTop: spacing.s4 },
                    ]}
                  >
                    <Text style={[typography.bodyEm, { color: '#fff', textAlign: 'center' }]}>
                      Sign out
                    </Text>
                  </Pressable>
                )}
              </Animated.ScrollView>
            </Animated.View>
          </GestureDetector>

          {/* Sub-panel scrim */}
          {subMounted && (
            <Animated.View
              style={[StyleSheet.absoluteFill, styles.subScrim, subScrimStyle]}
              pointerEvents="none"
            />
          )}

          {/* Sub-panel */}
          {subMounted && currentPanel && (
            <>
              <Pressable style={StyleSheet.absoluteFill} onPress={popSub} />

              {/* Background sheet — content-sized, shows prev panel (or current at depth 1) */}
              <GestureDetector gesture={subSheetGesture}>
                <Animated.View
                  style={[
                    styles.subSheet,
                    { backgroundColor: colors.bg2, paddingBottom: insets.bottom },
                    subSheetStyle,
                  ]}
                  pointerEvents={panelStack.length >= 2 ? 'none' : 'box-none'}
                >
                  <View style={styles.subHandleBar}>
                    <View style={[styles.handle, { backgroundColor: colors.bg3 }]} />
                  </View>
                  <View style={{ flex: 1, overflow: 'hidden' }}>
                    {renderPanel(prevPanel ?? currentPanel)}
                  </View>
                  {panelStack.length >= 2 && (
                    <View
                      style={[
                        StyleSheet.absoluteFill,
                        {
                          backgroundColor: 'rgba(0,0,0,0.3)',
                          borderTopLeftRadius: 20,
                          borderTopRightRadius: 20,
                        },
                      ]}
                      pointerEvents="none"
                    />
                  )}
                </Animated.View>
              </GestureDetector>

              {/* Top sheet — full height, slides in during push / slides out during pop */}
              {panelStack.length >= 2 && (
                <GestureDetector gesture={subSheetGesture}>
                  <Animated.View
                    style={[
                      styles.topSubSheet,
                      { backgroundColor: colors.bg2, paddingBottom: insets.bottom },
                      topSheetStyle,
                    ]}
                  >
                    <View style={styles.subHandleBar}>
                      <View style={[styles.handle, { backgroundColor: colors.bg3 }]} />
                    </View>
                    <View style={{ flex: 1, overflow: 'hidden' }}>{renderPanel(currentPanel)}</View>
                  </Animated.View>
                </GestureDetector>
              )}
            </>
          )}
        </View>
      </GestureHandlerRootView>
    </Modal>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.6)' },
  sheet: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingHorizontal: 16,
    paddingTop: 12,
    maxHeight: '90%',
  },
  handle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginBottom: 16 },
  profileRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
  },
  lifePlusBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  navRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
  iconChip: {
    width: 30,
    height: 30,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  signOut: { borderRadius: 12, padding: 14 },
  subScrim: { backgroundColor: 'rgba(0,0,0,0.35)' },
  subSheet: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    // Sizes to content; long panels that need scrolling (Subscription) wrap
    // their content in a height-bounded View inside renderPanel.
    maxHeight: SCREEN_HEIGHT * 0.9,
  },
  topSubSheet: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    // Top sub-panel hosts integration connect screens (AppleHealth, Garmin,
    // Yazio, Calendar, HA) which are short — size to content, no empty space.
    maxHeight: SCREEN_HEIGHT * 0.9,
  },
  subHandleBar: { paddingTop: 12, paddingBottom: 4, alignItems: 'center' },
});

// Shared styles for sub-panel content
const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  brandChip: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  connDot: { width: 6, height: 6, borderRadius: 3 },
  privacyNote: { padding: 14, borderRadius: 16, borderWidth: 1, borderStyle: 'dashed' },
});
