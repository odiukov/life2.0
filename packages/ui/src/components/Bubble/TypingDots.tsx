import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, View } from 'react-native';
import { useTheme } from '../../theme';

const DOT_COUNT = 3;
const PULSE_DURATION = 420;
const STAGGER = 140;

export function TypingDots({ testID }: { testID?: string }) {
  const { colors } = useTheme();
  const values = useRef(Array.from({ length: DOT_COUNT }, () => new Animated.Value(0.3))).current;

  useEffect(() => {
    const loops = values.map((val, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * STAGGER),
          Animated.timing(val, {
            toValue: 1,
            duration: PULSE_DURATION,
            useNativeDriver: true,
          }),
          Animated.timing(val, {
            toValue: 0.3,
            duration: PULSE_DURATION,
            useNativeDriver: true,
          }),
        ]),
      ),
    );
    loops.forEach((l) => l.start());
    return () => loops.forEach((l) => l.stop());
  }, [values]);

  return (
    <View testID={testID} style={styles.row} accessibilityLabel="agent-typing">
      {values.map((v, i) => (
        <Animated.View
          key={i}
          style={[
            styles.dot,
            { backgroundColor: colors.fg2, opacity: v, transform: [{ scale: v }] },
          ]}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', height: 20, gap: 5 },
  dot: { width: 6, height: 6, borderRadius: 3 },
});
