import { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';

/**
 * Provides onPressIn/onPressOut handlers + an animated style that scales a
 * card down slightly on press and springs back on release.
 */
export function usePressScale(toValue = 0.96) {
  const scale = useSharedValue(1);

  const onPressIn = () => {
    scale.value = withSpring(toValue, { damping: 22, stiffness: 450 });
  };

  const onPressOut = () => {
    scale.value = withSpring(1, { damping: 18, stiffness: 220 });
  };

  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  return { onPressIn, onPressOut, pressStyle };
}
