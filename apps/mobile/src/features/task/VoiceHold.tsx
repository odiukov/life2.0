import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  cancelAnimation,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withDelay,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import { useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { BUTTON_SIZE } from './TaskButton';

const BARS = [0.5, 0.8, 1, 0.7, 0.9, 0.6, 0.75];
const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

function Ring({ delay }: { delay: number }) {
  const { colors } = useTheme();
  const p = useSharedValue(0);
  useEffect(() => {
    p.value = withDelay(
      delay,
      withRepeat(withTiming(1, { duration: 1400, easing: Easing.out(Easing.quad) }), -1, false),
    );
    return () => cancelAnimation(p);
  }, [delay, p]);
  const style = useAnimatedStyle(() => ({
    opacity: 0.9 * (1 - p.value),
    transform: [{ scale: 1 + p.value * 1.6 }],
  }));
  return (
    <Animated.View
      pointerEvents="none"
      style={[styles.ring, { borderColor: colors.accentHi }, style]}
    />
  );
}

export function VoiceHold({
  seconds,
  level,
  armed,
  transcribing,
}: {
  seconds: number;
  level: number;
  armed: boolean;
  transcribing: boolean;
}) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  const reduceMotion = useReducedMotion();
  const label = transcribing
    ? t('task.hold.transcribing')
    : armed
      ? t('task.hold.cancel')
      : `${mmss(seconds)} · ${t('task.hold.hint')}`;
  return (
    <View pointerEvents="none" style={styles.wrap} testID="voice-hold">
      {!transcribing && !reduceMotion && (
        <View style={styles.rings}>
          <Ring delay={0} />
          <Ring delay={700} />
        </View>
      )}
      {!transcribing && (
        <View style={styles.wave}>
          {BARS.map((f, i) => (
            <View
              key={i}
              style={[
                styles.bar,
                {
                  backgroundColor: armed ? colors.danger : colors.accentHi,
                  height: 8 + Math.round(level * 32 * f),
                },
              ]}
            />
          ))}
        </View>
      )}
      <Text style={[styles.label, { color: armed ? colors.danger : colors.fg2 }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: { borderRadius: 2, width: 4 },
  label: { fontSize: 12, textAlign: 'center' },
  ring: {
    borderRadius: BUTTON_SIZE / 2,
    borderWidth: 2,
    height: BUTTON_SIZE,
    position: 'absolute',
    width: BUTTON_SIZE,
  },
  rings: {
    alignSelf: 'center',
    bottom: -(BUTTON_SIZE + 24) + 6,
    height: BUTTON_SIZE,
    position: 'absolute',
    width: BUTTON_SIZE,
  },
  wave: { alignItems: 'flex-end', flexDirection: 'row', gap: 4, height: 40 },
  wrap: {
    alignItems: 'center',
    bottom: BUTTON_SIZE + 24,
    gap: 10,
    left: -120,
    position: 'absolute',
    right: -120,
  },
});
