import React, { useCallback, useEffect, useState } from 'react';
import { Dimensions, Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { Gesture, GestureDetector, GestureHandlerRootView } from 'react-native-gesture-handler';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '@life-agents/ui';
import { BACKDROP_IN_MS, BACKDROP_OUT_MS, EXIT_MS, SHEET_SPRING } from '@/lib/sheetAnimation';
import { useSwipeToDismiss } from '@/lib/useSwipeToDismiss';
import { useIntegrationsStore, type IntegrationId } from './store';
import { AppleHealthPanel } from './panels/AppleHealthPanel';
import { GarminPanel } from './panels/GarminPanel';
import { GoogleCalendarPanel } from './panels/GoogleCalendarPanel';
import { HaPanel } from './panels/HaPanel';
import { YazioPanel } from './panels/YazioPanel';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');

const INTEGRATION_LABEL: Record<IntegrationId, string> = {
  'apple-health': 'Apple Health',
  garmin: 'Garmin Connect',
  yazio: 'Yazio',
  calendar: 'Google Calendar',
  ha: 'Home Assistant',
  strava: 'Strava',
  payoneer: 'Payoneer',
};

type Props = {
  integration: IntegrationId | null;
  onClose: () => void;
  // Fires synchronously when a user-initiated close animation begins. Parents
  // use this to unwind their own card-stack push-back so it lands in step
  // with the sheet exit.
  onAnimateClose?: () => void;
};

export function IntegrationSheet({ integration, onClose, onAnimateClose }: Props) {
  const { colors, typography } = useTheme();
  const insets = useSafeAreaInsets();
  const [mounted, setMounted] = useState(false);
  const [rendered, setRendered] = useState<IntegrationId | null>(null);

  const sheetY = useSharedValue(SCREEN_HEIGHT);
  const scrimAlpha = useSharedValue(0);

  useEffect(() => {
    if (integration && !mounted) {
      setRendered(integration);
      setMounted(true);
    }
  }, [integration, mounted]);

  useEffect(() => {
    if (mounted) {
      sheetY.value = SCREEN_HEIGHT;
      scrimAlpha.value = withTiming(1, {
        duration: BACKDROP_IN_MS,
        easing: Easing.out(Easing.quad),
      });
      sheetY.value = withSpring(0, SHEET_SPRING);
    }
  }, [mounted]);

  const finishClose = useCallback(() => {
    setMounted(false);
    setRendered(null);
    onClose();
  }, [onClose]);

  const animateOutAndClose = useCallback(() => {
    onAnimateClose?.();
    scrimAlpha.value = withTiming(0, {
      duration: BACKDROP_OUT_MS,
      easing: Easing.in(Easing.quad),
    });
    sheetY.value = withTiming(
      SCREEN_HEIGHT,
      { duration: EXIT_MS, easing: Easing.in(Easing.cubic) },
      (finished) => {
        if (finished) runOnJS(finishClose)();
      },
    );
  }, [onAnimateClose, finishClose, scrimAlpha, sheetY]);

  // Parent-initiated close: integration was set to null while still mounted.
  useEffect(() => {
    if (!integration && mounted && rendered) animateOutAndClose();
  }, [integration, mounted, rendered, animateOutAndClose]);

  const { panGesture, scrollHandler } = useSwipeToDismiss({
    sheetY,
    backdropAlpha: scrimAlpha,
    onClose: finishClose,
    onCloseStart: onAnimateClose,
    enabled: mounted,
  });
  // Native gesture lets inner ScrollViews scroll vertically; our pan only
  // activates after a clear downward dismiss swipe.
  const gesture = Gesture.Simultaneous(panGesture, Gesture.Native());

  const scrimStyle = useAnimatedStyle(() => ({ opacity: scrimAlpha.value }));
  const sheetStyle = useAnimatedStyle(() => ({ transform: [{ translateY: sheetY.value }] }));

  function renderPanel() {
    if (!rendered) return null;
    const setStoreStatus = useIntegrationsStore.getState().set;
    const cb = {
      onConnected: () => setStoreStatus(rendered, 'connected'),
      onDisconnected: () => setStoreStatus(rendered, 'not-connected'),
    };
    const scrollProps = { onScroll: scrollHandler, scrollEventThrottle: 16 };
    switch (rendered) {
      case 'apple-health':
        return (
          <Animated.ScrollView {...scrollProps}>
            <AppleHealthPanel {...cb} />
          </Animated.ScrollView>
        );
      case 'garmin':
        return <GarminPanel {...cb} {...scrollProps} />;
      case 'yazio':
        return <YazioPanel {...cb} {...scrollProps} />;
      case 'calendar':
        return <GoogleCalendarPanel {...cb} {...scrollProps} />;
      case 'ha':
        return <HaPanel {...cb} {...scrollProps} />;
      default:
        return null;
    }
  }

  if (!mounted) return null;

  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={animateOutAndClose}
      statusBarTranslucent
    >
      <GestureHandlerRootView style={{ flex: 1 }}>
        <Animated.View style={[styles.scrim, scrimStyle]} pointerEvents="none" />
        <Pressable style={StyleSheet.absoluteFill} onPress={animateOutAndClose} />

        <GestureDetector gesture={gesture}>
          <Animated.View
            style={[
              styles.sheet,
              { backgroundColor: colors.bg2, paddingBottom: insets.bottom },
              sheetStyle,
            ]}
          >
            <View style={[styles.handle, { backgroundColor: colors.bg3 }]} />
            <View style={[styles.header, { borderBottomColor: colors.border }]}>
              <Text style={[typography.title2, { color: colors.fg1 }]}>
                {rendered ? INTEGRATION_LABEL[rendered] : ''}
              </Text>
            </View>
            {renderPanel()}
          </Animated.View>
        </GestureDetector>
      </GestureHandlerRootView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingTop: 12,
    maxHeight: '85%',
  },
  handle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginBottom: 20 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
});
