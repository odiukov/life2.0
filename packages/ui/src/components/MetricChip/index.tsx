import React from 'react';
import { StyleSheet, Text, View, ViewProps } from 'react-native';
import { useTheme } from '../../theme';

type Variant = 'up' | 'down' | 'neu';

export function MetricChip({
  children,
  variant = 'neu',
  ...rest
}: { children: React.ReactNode; variant?: Variant } & ViewProps) {
  const { colors, typography, radius, spacing } = useTheme();
  const color =
    variant === 'up' ? colors.success : variant === 'down' ? colors.danger : colors.fg1;
  return (
    <View
      style={[
        styles.chip,
        {
          backgroundColor: colors.bg3,
          borderColor: colors.border,
          borderRadius: radius.rXs,
          paddingHorizontal: spacing.s2,
          paddingVertical: 2,
        },
      ]}
      {...rest}
    >
      <Text style={[typography.mono, { color, fontVariant: ['tabular-nums'] }]}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: { alignSelf: 'flex-start', borderWidth: 1 },
});
