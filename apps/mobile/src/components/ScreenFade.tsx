import React, { useCallback } from 'react';
import { View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  Easing,
  cancelAnimation,
} from 'react-native-reanimated';
import { useFocusEffect } from 'expo-router';

const BG = '#0f0f13';

type Props = {
  children: React.ReactNode;
};

export function ScreenFade({ children }: Props) {
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(8);

  useFocusEffect(
    useCallback(() => {
      cancelAnimation(opacity);
      cancelAnimation(translateY);
      opacity.value = 0;
      translateY.value = 8;
      opacity.value = withTiming(1, { duration: 220, easing: Easing.out(Easing.ease) });
      translateY.value = withTiming(0, { duration: 220, easing: Easing.out(Easing.ease) });
    }, [opacity, translateY]),
  );

  const animStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));

  return (
    // Outer View always opaque — prevents native white showing through
    // when Animated.View is transparent or shifted
    <View style={{ flex: 1, backgroundColor: BG }}>
      <Animated.View style={[{ flex: 1 }, animStyle]}>
        {children}
      </Animated.View>
    </View>
  );
}
