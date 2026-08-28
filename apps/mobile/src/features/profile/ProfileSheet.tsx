import React, { useEffect, useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, View, Alert } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { useTheme } from '@life-agents/ui';
import { supabase, SUPABASE_CONFIGURED } from '@/features/auth/SupabaseClient';
import {
  type IntegrationId,
  isConnected,
  useIntegrationsStore,
} from '@/features/integrations/store';
import { IntegrationSheet } from '@/features/integrations/IntegrationSheet';
import { AGENT_COLOR } from '@/features/dash/agentMeta';
import { useSheetAnimation, SHEET_SPRING } from '@/lib/sheetAnimation';
import { GestureDetector, GestureHandlerRootView } from 'react-native-gesture-handler';
import { useSwipeToDismiss } from '@/lib/useSwipeToDismiss';

type Props = { visible: boolean; onClose: () => void; userEmail?: string; displayName?: string };

type IntegrationConfig = {
  id: IntegrationId;
  label: string;
  emoji: string;
};

const INTEGRATIONS: IntegrationConfig[] = [
  { id: 'apple-health', label: 'Apple Health', emoji: '🍎' },
  { id: 'garmin', label: 'Garmin Connect', emoji: '⌚' },
  { id: 'yazio', label: 'Yazio', emoji: '🥗' },
  { id: 'calendar', label: 'Google Calendar', emoji: '📅' },
  { id: 'ha', label: 'Home Assistant', emoji: '🏠' },
];

export function ProfileSheet({ visible, onClose, userEmail, displayName }: Props) {
  const { colors, radius, spacing, typography } = useTheme();
  const [activeIntegration, setActiveIntegration] = useState<IntegrationId | null>(null);
  const status = useIntegrationsStore((s) => s.status);

  const {
    mounted: modalMounted,
    sheetY,
    backdropAlpha,
    backdropStyle,
  } = useSheetAnimation(visible);
  const { panGesture: rootPanGesture, scrollHandler: rootScrollHandler } = useSwipeToDismiss({
    sheetY,
    backdropAlpha,
    onClose,
  });

  // Card-stack push-back applied while the integration sheet is open
  const profileScale = useSharedValue(1);
  const profileTranslateY = useSharedValue(0);

  const initials = (displayName ?? userEmail ?? 'U')
    .split(' ')
    .map((w) => w[0] ?? '')
    .join('')
    .toUpperCase()
    .slice(0, 2);

  function pushBack() {
    profileScale.value = withSpring(0.93, SHEET_SPRING);
    profileTranslateY.value = withSpring(-10, SHEET_SPRING);
  }

  function restorePush() {
    profileScale.value = withSpring(1, SHEET_SPRING);
    profileTranslateY.value = withSpring(0, SHEET_SPRING);
  }

  function handleIntegrationPress(id: IntegrationId) {
    setActiveIntegration(id);
    pushBack();
  }

  // Defensive reset when the parent sheet is dismissed externally (e.g.
  // Android back button) while an integration is layered on top — without
  // this, re-opening the sheet would replay the lingering state.
  useEffect(() => {
    if (!visible) {
      setActiveIntegration(null);
      profileScale.value = 1;
      profileTranslateY.value = 0;
    }
  }, [visible]);

  async function handleSignOut() {
    onClose();
    if (SUPABASE_CONFIGURED) await supabase.auth.signOut();
  }

  const sheetStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: sheetY.value },
      { scale: profileScale.value },
      { translateY: profileTranslateY.value },
    ],
  }));

  if (!modalMounted) return null;

  return (
    <Modal
      visible={modalMounted}
      transparent
      animationType="none"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <GestureHandlerRootView style={{ flex: 1 }}>
        <View style={styles.overlay}>
          <Animated.View style={[styles.backdrop, backdropStyle]} pointerEvents="none" />
          <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />

          <GestureDetector gesture={rootPanGesture}>
            <Animated.View style={[styles.sheet, { backgroundColor: colors.bg2 }, sheetStyle]}>
              <View style={[styles.handle, { backgroundColor: colors.bg3 }]} />
              <Animated.ScrollView
                onScroll={rootScrollHandler}
                scrollEventThrottle={16}
                showsVerticalScrollIndicator={false}
                contentContainerStyle={{ paddingBottom: 32 }}
              >
                <View style={[styles.userRow, { marginBottom: spacing.s5 }]}>
                  <View
                    style={[
                      styles.avatar,
                      { borderRadius: 26, backgroundColor: AGENT_COLOR.sleep },
                    ]}
                  >
                    <Text style={[typography.title1, { color: '#fff' }]}>{initials}</Text>
                  </View>
                  <View>
                    <Text style={[typography.title2, { color: colors.fg1 }]}>
                      {displayName ?? 'Profile'}
                    </Text>
                    <Text style={[typography.caption, { color: colors.fg3 }]}>
                      {userEmail ?? ''}
                    </Text>
                  </View>
                </View>

                <Text
                  style={[
                    typography.micro,
                    {
                      color: colors.fg3,
                      textTransform: 'uppercase',
                      letterSpacing: 0.5,
                      marginBottom: spacing.s3,
                    },
                  ]}
                >
                  Integrations
                </Text>
                <View style={[styles.section, { marginBottom: spacing.s5 }]}>
                  {INTEGRATIONS.map((cfg, i) => {
                    const connected = isConnected(status[cfg.id]);
                    return (
                      <Pressable
                        key={cfg.id}
                        onPress={() => handleIntegrationPress(cfg.id)}
                        style={[
                          styles.row,
                          { backgroundColor: colors.bg3, padding: spacing.s3 },
                          i === 0 && {
                            borderTopLeftRadius: radius.rMd,
                            borderTopRightRadius: radius.rMd,
                          },
                          i === INTEGRATIONS.length - 1 && {
                            borderBottomLeftRadius: radius.rMd,
                            borderBottomRightRadius: radius.rMd,
                          },
                        ]}
                      >
                        <Text style={{ fontSize: 16, width: 28 }}>{cfg.emoji}</Text>
                        <Text
                          style={[
                            typography.body,
                            { color: colors.fg1, flex: 1, fontWeight: '500' },
                          ]}
                        >
                          {cfg.label}
                        </Text>
                        <View
                          style={[
                            styles.badge,
                            {
                              backgroundColor: connected ? '#10b98120' : colors.bg2,
                              borderColor: connected ? '#10b98140' : colors.border,
                            },
                          ]}
                        >
                          <Text
                            style={[
                              typography.caption,
                              { color: connected ? '#10b981' : colors.fg3 },
                            ]}
                          >
                            {connected ? 'Active' : 'Connect'}
                          </Text>
                        </View>
                      </Pressable>
                    );
                  })}
                </View>

                <Text
                  style={[
                    typography.micro,
                    {
                      color: colors.fg3,
                      textTransform: 'uppercase',
                      letterSpacing: 0.5,
                      marginBottom: spacing.s3,
                    },
                  ]}
                >
                  Settings
                </Text>
                <View style={styles.section}>
                  <Pressable
                    style={[
                      styles.row,
                      {
                        backgroundColor: colors.bg3,
                        padding: spacing.s3,
                        borderTopLeftRadius: radius.rMd,
                        borderTopRightRadius: radius.rMd,
                      },
                    ]}
                    onPress={() => Alert.alert('Notifications', 'Coming soon')}
                  >
                    <Text style={{ fontSize: 16, width: 28 }}>🔔</Text>
                    <Text
                      style={[typography.body, { color: colors.fg1, flex: 1, fontWeight: '500' }]}
                    >
                      Notifications
                    </Text>
                    <Text style={[typography.body, { color: colors.fg3 }]}>›</Text>
                  </Pressable>
                  <Pressable
                    style={[styles.row, { backgroundColor: colors.bg3, padding: spacing.s3 }]}
                    onPress={() => Alert.alert('Goals', 'Coming soon')}
                  >
                    <Text style={{ fontSize: 16, width: 28 }}>🎯</Text>
                    <Text
                      style={[typography.body, { color: colors.fg1, flex: 1, fontWeight: '500' }]}
                    >
                      Goals
                    </Text>
                    <Text style={[typography.body, { color: colors.fg3 }]}>›</Text>
                  </Pressable>
                  <Pressable
                    style={[
                      styles.row,
                      {
                        backgroundColor: colors.bg3,
                        padding: spacing.s3,
                        borderBottomLeftRadius: radius.rMd,
                        borderBottomRightRadius: radius.rMd,
                      },
                    ]}
                    onPress={handleSignOut}
                  >
                    <Text style={{ fontSize: 16, width: 28 }}>🚪</Text>
                    <Text
                      style={[typography.body, { color: '#e11d48', flex: 1, fontWeight: '500' }]}
                    >
                      Sign out
                    </Text>
                  </Pressable>
                </View>
              </Animated.ScrollView>
            </Animated.View>
          </GestureDetector>

          <IntegrationSheet
            integration={activeIntegration}
            onAnimateClose={restorePush}
            onClose={() => setActiveIntegration(null)}
          />
        </View>
      </GestureHandlerRootView>
    </Modal>
  );
}

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
  handle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginBottom: 20 },
  userRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  avatar: { width: 52, height: 52, alignItems: 'center', justifyContent: 'center' },
  section: { gap: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  badge: { borderWidth: 1, borderRadius: 6, paddingHorizontal: 8, paddingVertical: 3 },
});
