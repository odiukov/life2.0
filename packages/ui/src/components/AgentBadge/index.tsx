import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../../theme';

export type AgentId =
  | 'sleep' | 'workout' | 'nutrition' | 'mood'
  | 'habits' | 'recovery' | 'medication' | 'finance'
  | 'calendar' | 'home';

export function AgentBadge({ agent }: { agent: AgentId }) {
  const { colors, typography, radius, spacing } = useTheme();
  return (
    <View
      style={[
        styles.badge,
        {
          backgroundColor: colors.bg3,
          borderRadius: radius.rXs,
          paddingHorizontal: spacing.s2,
          paddingVertical: 2,
        },
      ]}
    >
      <Text style={[typography.micro, { color: colors.accentHi }]}>{agent.toUpperCase()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({ badge: { alignSelf: 'flex-start' } });
