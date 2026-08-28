import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../../theme';
import { AgentMark } from '../AgentMark';
import { AgentChip } from '../AgentChip';
import type { AgentId } from '../AgentBadge';

export function AgentHeader({
  primary,
  consulted = [],
  testID,
}: {
  primary: AgentId;
  consulted?: readonly AgentId[];
  testID?: string;
}) {
  const { colors, typography, spacing } = useTheme();
  return (
    <View testID={testID} style={{ alignItems: 'flex-start' }}>
      <View style={[styles.headerRow, { gap: spacing.s2 }]}>
        <AgentMark agent={primary} size={28} />
        <Text style={[typography.micro, { color: colors.fg2 }]}>{primary.toUpperCase()}</Text>
      </View>
      {consulted.length > 0 && (
        <View style={[styles.viaRow, { marginTop: 4, marginLeft: 36, gap: 6 }]}>
          <Text style={[typography.micro, { color: colors.fg3 }]}>via</Text>
          {consulted.map((peer) => (
            <AgentChip key={peer} agent={peer} tone="on-bubble" size="sm" />
          ))}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: 'row', alignItems: 'center' },
  viaRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' },
});
