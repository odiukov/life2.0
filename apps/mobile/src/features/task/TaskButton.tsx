import React, { useCallback, useEffect, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  Easing,
  cancelAnimation,
  runOnJS,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withSpring,
  withTiming,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { Icon, useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { haptic } from '@/lib/haptics';
import { useVoiceInput } from '@/features/voice/useVoiceInput';
import { VoiceHold } from './VoiceHold';
import { CANCEL_DX, classifyPress, HOLD_MS } from './classifyPress';
import { openTask, type Point } from './sheetStore';

import { BUTTON_SIZE } from './dimensions';
export { BUTTON_SIZE } from './dimensions';
const PRESS_SPRING = { damping: 14, stiffness: 420, mass: 0.6 } as const;
const BREATH_MS = 1500;

export function TaskButton() {
  const { colors } = useTheme();
  const t = useT(appLocale());
  const ref = useRef<View>(null);
  const origin = useRef<Point | null>(null);
  const scale = useSharedValue(1);
  const glow = useSharedValue(0);
  const reduceMotion = useReducedMotion();

  useEffect(() => {
    if (reduceMotion) return;
    glow.value = withRepeat(
      withTiming(1, { duration: BREATH_MS, easing: Easing.inOut(Easing.sin) }),
      -1,
      true,
    );
    return () => cancelAnimation(glow);
  }, [reduceMotion, glow]);

  const measure = useCallback(() => {
    ref.current?.measureInWindow((x, y, w, h) => {
      origin.current = { x: x + w / 2, y: y + h / 2 };
    });
  }, []);
  const open = useCallback(
    () => openTask(origin.current ? { origin: origin.current } : undefined),
    [],
  );
  const pressIn = useCallback(() => haptic('light'), []);

  const [holding, setHolding] = useState(false);
  const [armed, setArmed] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const holdingRef = useRef(false);
  const armedSV = useSharedValue(false);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flash = useCallback((text: string) => {
    setNotice(text);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), 3000);
  }, []);
  useEffect(
    () => () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    },
    [],
  );

  const voice = useVoiceInput({
    onTranscript: (text, seconds) => {
      haptic('success');
      openTask({ ...(origin.current ? { origin: origin.current } : {}), voice: { text, seconds } });
    },
    onNotice: flash,
    onFinished: () => {
      holdingRef.current = false;
      setHolding(false);
      setArmed(false);
    },
  });

  const beginHold = useCallback(() => {
    holdingRef.current = true;
    haptic('medium');
    setHolding(true);
    setArmed(false);
    void voice.start();
  }, [voice]);

  const endHold = useCallback(
    (dx: number) => {
      if (!holdingRef.current) return;
      holdingRef.current = false;
      setHolding(false);
      setArmed(false);
      if (classifyPress({ held: true, dx }) === 'cancel') {
        haptic('warning');
        void voice.cancel();
      } else {
        void voice.stop();
      }
    },
    [voice],
  );

  const abortHold = useCallback(() => {
    if (!holdingRef.current) return;
    holdingRef.current = false;
    setHolding(false);
    setArmed(false);
    void voice.cancel();
  }, [voice]);

  const tap = Gesture.Tap()
    .maxDuration(HOLD_MS)
    .onBegin(() => {
      scale.value = withSpring(0.92, PRESS_SPRING);
      runOnJS(pressIn)();
    })
    .onEnd((_e, success) => {
      if (success) runOnJS(open)();
    })
    .onFinalize(() => {
      scale.value = withSpring(1, PRESS_SPRING);
    })
    .withTestId('task-button-tap');

  const hold = Gesture.Pan()
    .activateAfterLongPress(HOLD_MS)
    .onStart(() => {
      armedSV.value = false;
      scale.value = withSpring(1.25, PRESS_SPRING);
      runOnJS(beginHold)();
    })
    .onUpdate((e) => {
      const next = e.translationX < CANCEL_DX;
      if (next !== armedSV.value) {
        armedSV.value = next;
        runOnJS(setArmed)(next);
      }
    })
    .onEnd((e) => {
      runOnJS(endHold)(e.translationX);
    })
    .onFinalize(() => {
      scale.value = withSpring(1, PRESS_SPRING);
      runOnJS(abortHold)(); // no-op after onEnd; cancels when the system interrupts the hold
    })
    .withTestId('task-button-hold');

  const gesture = Gesture.Exclusive(hold, tap);

  const buttonStyle = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const haloStyle = useAnimatedStyle(() => ({
    opacity: 0.25 + glow.value * 0.3,
    transform: [{ scale: 1 + glow.value * 0.14 }],
  }));

  return (
    <GestureDetector gesture={gesture}>
      <View
        ref={ref}
        onLayout={measure}
        testID="task-button"
        accessible
        accessibilityRole="button"
        accessibilityLabel={t('task.button')}
        accessibilityHint={t('task.button_hint')}
        onAccessibilityTap={open}
        style={styles.wrap}
      >
        {(holding || voice.state === 'transcribing') && (
          <VoiceHold
            seconds={voice.seconds}
            level={voice.level}
            armed={armed}
            transcribing={voice.state === 'transcribing'}
          />
        )}
        {notice && <Text style={[styles.notice, { color: colors.fg2 }]}>{notice}</Text>}
        <Animated.View
          pointerEvents="none"
          style={[styles.halo, { backgroundColor: colors.accent }, haloStyle]}
        />
        <Animated.View style={[styles.button, { borderColor: colors.bg0 }, buttonStyle]}>
          <LinearGradient
            colors={[colors.accentHi, colors.accent]}
            start={{ x: 0.2, y: 0 }}
            end={{ x: 0.8, y: 1 }}
            style={styles.fill}
          >
            <Icon
              name={holding ? 'Microphone' : 'Sparkle'}
              size={26}
              color={colors.accentInk}
              weight="fill"
            />
          </LinearGradient>
        </Animated.View>
      </View>
    </GestureDetector>
  );
}

const styles = StyleSheet.create({
  button: {
    borderRadius: BUTTON_SIZE / 2,
    borderWidth: 6,
    height: BUTTON_SIZE,
    overflow: 'hidden',
    width: BUTTON_SIZE,
  },
  fill: { alignItems: 'center', flex: 1, justifyContent: 'center' },
  halo: {
    borderRadius: (BUTTON_SIZE + 12) / 2,
    height: BUTTON_SIZE + 12,
    position: 'absolute',
    width: BUTTON_SIZE + 12,
  },
  notice: { bottom: BUTTON_SIZE + 24, position: 'absolute', textAlign: 'center', width: 300 },
  wrap: {
    alignItems: 'center',
    height: BUTTON_SIZE + 12,
    justifyContent: 'center',
    marginTop: -28,
    width: BUTTON_SIZE + 12,
  },
});
