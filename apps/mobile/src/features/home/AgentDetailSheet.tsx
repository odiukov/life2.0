import React, { useRef } from 'react';
import { Modal, Pressable, StyleSheet, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { Gesture, GestureDetector, GestureHandlerRootView } from 'react-native-gesture-handler';
import { useRouter } from 'expo-router';
import { useTheme } from '@life-agents/ui';
import type { AgentId } from '@life-agents/ui';
import { useSheetAnimation } from '@/lib/sheetAnimation';
import { useSwipeToDismiss } from '@/lib/useSwipeToDismiss';
import { AgentDetailContent } from './AgentDetailContent';

type Props = {
  visible: boolean;
  agentId: AgentId | null;
  onClose: () => void;
};

const BACKDROP_COLOR = 'rgba(0,0,0,0.6)';

export function AgentDetailSheet({ visible, agentId, onClose }: Props) {
  const { colors } = useTheme();
  const router = useRouter();

  // Keep last agentId alive across the exit animation: when the parent sets
  // visible=false it usually nulls agentId in the same render, but the sheet
  // stays mounted ~210ms while sliding out. Render the last known content.
  const lastAgentIdRef = useRef<AgentId | null>(null);
  if (agentId !== null) lastAgentIdRef.current = agentId;
  const activeAgentId = agentId ?? lastAgentIdRef.current;

  const { mounted, sheetY, backdropAlpha, backdropStyle, sheetStyle } = useSheetAnimation(visible);
  const { panGesture, scrollHandler } = useSwipeToDismiss({
    sheetY,
    backdropAlpha,
    onClose,
  });
  const gesture = Gesture.Simultaneous(panGesture, Gesture.Native());

  if (!mounted || !activeAgentId) return null;

  function handleAction(message: string) {
    onClose();
    const tagged = `/${activeAgentId} ${message}`;
    setTimeout(() => {
      router.push({ pathname: '/(tabs)/chat', params: { send: tagged } } as never);
    }, 150);
  }

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
          <Animated.View style={[styles.backdrop, backdropStyle]} pointerEvents="none" />
          <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />

          <GestureDetector gesture={gesture}>
            <Animated.View style={[styles.sheet, { backgroundColor: colors.bg1 }, sheetStyle]}>
              <View style={[styles.handle, { backgroundColor: colors.bg3 }]} />

              <Animated.ScrollView
                onScroll={scrollHandler}
                scrollEventThrottle={16}
                showsVerticalScrollIndicator={false}
                contentContainerStyle={styles.scrollContent}
              >
                <AgentDetailContent
                  agentId={activeAgentId}
                  enabled={visible}
                  onAction={handleAction}
                />
              </Animated.ScrollView>
            </Animated.View>
          </GestureDetector>
        </View>
      </GestureHandlerRootView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: BACKDROP_COLOR },
  handle: { alignSelf: 'center', borderRadius: 2, height: 4, marginBottom: 8, width: 36 },
  overlay: { flex: 1, justifyContent: 'flex-end' },
  root: { flex: 1 },
  scrollContent: { paddingBottom: 32, paddingHorizontal: 16 },
  sheet: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '92%',
    paddingTop: 8,
  },
});
