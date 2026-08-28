import { useEffect, useRef, useState } from 'react';
import { Dimensions } from 'react-native';
import {
  Easing,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from 'react-native-reanimated';

const { height: SCREEN_HEIGHT } = Dimensions.get('window');

export const SHEET_SPRING = { damping: 28, stiffness: 380, mass: 0.9 } as const;
export const BACKDROP_IN_MS = 230;
export const BACKDROP_OUT_MS = 160;
export const EXIT_MS = 210;

/**
 * Manages bottom-sheet mount, backdrop fade, and slide-up/down animation.
 *
 * Returns `mounted` for the Modal's `visible` prop, animated styles for the
 * backdrop and sheet, and the raw `sheetY` shared value for callers that need
 * to compose additional transforms (e.g. card-stack scale on top of translateY).
 */
export function useSheetAnimation(visible: boolean) {
  const [mounted, setMounted] = useState(false);
  const sheetY = useSharedValue(SCREEN_HEIGHT);
  const backdropAlpha = useSharedValue(0);
  const prevMounted = useRef(false);

  function animateIn() {
    sheetY.value = SCREEN_HEIGHT;
    backdropAlpha.value = 0;
    backdropAlpha.value = withTiming(1, { duration: BACKDROP_IN_MS, easing: Easing.out(Easing.quad) });
    sheetY.value = withSpring(0, SHEET_SPRING);
  }

  function animateOut(done: () => void) {
    backdropAlpha.value = withTiming(0, { duration: BACKDROP_OUT_MS, easing: Easing.in(Easing.quad) });
    sheetY.value = withTiming(
      SCREEN_HEIGHT,
      { duration: EXIT_MS, easing: Easing.in(Easing.cubic) },
      (finished) => { if (finished) runOnJS(done)(); },
    );
  }

  useEffect(() => {
    if (visible) {
      setMounted(true);
    } else {
      animateOut(() => setMounted(false));
    }
  }, [visible]);

  // Trigger enter animation the first time the modal becomes mounted
  useEffect(() => {
    if (mounted && !prevMounted.current) animateIn();
    prevMounted.current = mounted;
  }, [mounted]);

  const backdropStyle = useAnimatedStyle(() => ({ opacity: backdropAlpha.value }));

  // Simple sheet style — consumers that need extra transforms can use `sheetY` directly
  const sheetStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: sheetY.value }],
  }));

  return { mounted, sheetY, backdropAlpha, backdropStyle, sheetStyle };
}
