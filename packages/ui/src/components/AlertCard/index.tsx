import React from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { useTheme } from '../../theme';

type Tone = 'info' | 'warn' | 'danger';

export function AlertCard({
  title,
  body,
  tone = 'info',
  timestamp,
  onPress,
}: {
  title?: string;
  body: string;
  tone?: Tone;
  timestamp?: string;
  onPress?: () => void;
}) {
  const { colors, radius, spacing, typography } = useTheme();
  const accent = { info: colors.accent, warn: colors.warn, danger: colors.danger }[tone];
  return (
    <Pressable
      testID="alert-card"
      onPress={onPress}
      style={[
        styles.card,
        {
          backgroundColor: colors.bg2,
          borderColor: colors.border,
          borderLeftColor: accent,
          borderLeftWidth: 3,
          borderRadius: radius.rMd,
          padding: spacing.s3,
        },
      ]}
    >
      {title ? (
        <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{title}</Text>
      ) : null}
      <Text
        style={[
          typography.body,
          { color: colors.fg2, marginTop: title ? spacing.s1 : 0 },
        ]}
      >
        {body}
      </Text>
      {timestamp && (
        <Text style={[typography.caption, { color: colors.fg3, marginTop: spacing.s2 }]}>{timestamp}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({ card: { borderWidth: 1 } });
