import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../../theme';

type Variant = 'assistant' | 'user' | 'log' | 'alert';

export function Bubble({
  children,
  variant = 'assistant',
  accentTone,
}: {
  children: React.ReactNode;
  variant?: Variant;
  accentTone?: 'warn' | 'danger';
}) {
  const { colors, radius, spacing, typography } = useTheme();
  const tones = {
    assistant: { bg: colors.bg2, border: colors.border, fg: colors.fg1, align: 'flex-start' as const },
    user:      { bg: colors.accentSoft, border: colors.accentBorder, fg: colors.fg1, align: 'flex-end' as const },
    log:       { bg: colors.bg2, border: colors.border, fg: colors.fg1, align: 'flex-start' as const },
    alert:     { bg: colors.bg2, border: colors.border, fg: colors.fg1, align: 'flex-start' as const },
  };
  const t = tones[variant];
  const sideAccent =
    variant === 'alert' && accentTone
      ? accentTone === 'warn' ? colors.warn : colors.danger
      : undefined;
  return (
    <View style={{ alignSelf: t.align, maxWidth: '85%' }}>
      <View
        style={[
          styles.bubble,
          {
            backgroundColor: t.bg,
            borderColor: t.border,
            borderRadius: radius.rMd,
            paddingHorizontal: spacing.s3,
            paddingVertical: spacing.s2,
            borderLeftColor: sideAccent ?? t.border,
            borderLeftWidth: sideAccent ? 3 : 1,
          },
        ]}
      >
        {typeof children === 'string' ? (
          <Text style={[typography.body, { color: t.fg }]}>{children}</Text>
        ) : (
          children
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({ bubble: { borderWidth: 1 } });
