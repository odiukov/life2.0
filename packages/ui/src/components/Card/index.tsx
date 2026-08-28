import React from 'react';
import { Pressable, StyleSheet, View, type ViewStyle } from 'react-native';
import { useTheme } from '../../theme';

interface CardProps {
  children: React.ReactNode;
  pad?: number;
  onPress?: () => void;
  style?: ViewStyle;
  testID?: string;
}

export function Card({ children, pad, onPress, style, testID }: CardProps) {
  const { colors, spacing, radius } = useTheme();
  const containerStyle: ViewStyle = {
    backgroundColor: colors.bg2,
    borderColor: colors.border,
    borderRadius: radius.rLg,
    borderWidth: 1,
    padding: pad ?? spacing.s4,
    ...style,
  };

  if (onPress) {
    return (
      <Pressable testID={testID} onPress={onPress} style={({ pressed }) => [containerStyle, pressed && styles.pressed]}>
        {children}
      </Pressable>
    );
  }

  return (
    <View testID={testID} style={containerStyle}>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  pressed: { opacity: 0.8 },
});
