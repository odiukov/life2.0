import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../../theme';

type Tone = 'success' | 'warn' | 'danger' | 'neu';

export function StatusPill({ tone = 'neu', children }: { tone?: Tone; children: React.ReactNode }) {
  const { colors, spacing, typography } = useTheme();
  const toneColor = {
    success: colors.success,
    warn: colors.warn,
    danger: colors.danger,
    neu: colors.fg2,
  }[tone];
  return (
    <View
      style={[
        styles.pill,
        {
          backgroundColor: colors.bg2,
          borderColor: colors.border,
          borderRadius: 999,
          paddingHorizontal: spacing.s3,
          paddingVertical: spacing.s1,
        },
      ]}
    >
      <View
        style={{
          width: 6,
          height: 6,
          borderRadius: 3,
          backgroundColor: toneColor,
          marginRight: spacing.s2,
        }}
      />
      <Text style={[typography.caption, { color: colors.fg1 }]}>{children}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: { alignItems: 'center', alignSelf: 'flex-start', borderWidth: 1, flexDirection: 'row' },
});
