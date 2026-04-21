import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../../theme';
import { AgentMark } from '../AgentMark';
import type { AgentId } from '../AgentBadge';

type Tint = 'success' | 'warn' | 'danger' | 'neutral';

export function AgentCard({
  agent,
  label,
  metric,
  tint = 'neutral',
  onPress,
}: {
  agent: AgentId;
  label: string;
  metric: string;
  tint?: Tint;
  onPress?: (agent: AgentId) => void;
}) {
  const { colors, radius, spacing, typography } = useTheme();
  const tintColor = {
    success: colors.success,
    warn: colors.warn,
    danger: colors.danger,
    neutral: colors.fg2,
  }[tint];
  return (
    <Pressable
      testID={`agent-card-${agent}`}
      onPress={() => onPress?.(agent)}
      style={[
        styles.card,
        {
          backgroundColor: colors.bg2,
          borderColor: colors.border,
          borderRadius: radius.rMd,
          padding: spacing.s3,
        },
      ]}
    >
      <View style={[styles.row, { marginBottom: spacing.s2 }]}>
        <AgentMark agent={agent} size={20} color={tintColor} />
        <Text style={[typography.bodyEm, { color: colors.fg1, marginLeft: spacing.s2 }]}>{label}</Text>
      </View>
      <Text style={[typography.mono, { color: tintColor, fontVariant: ['tabular-nums'] }]}>{metric}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1 },
  row: { alignItems: 'center', flexDirection: 'row' },
});
