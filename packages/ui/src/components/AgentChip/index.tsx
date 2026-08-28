import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../../theme';
import { AgentMark } from '../AgentMark';
import { agentSolid, agentTint } from '../../tokens/agentColors';
import type { AgentId } from '../AgentBadge';

export type AgentChipTone = 'on-bubble' | 'on-user-bubble' | 'on-input';
export type AgentChipSize = 'sm' | 'md';

export function AgentChip({
  agent,
  tone = 'on-bubble',
  size = 'sm',
  removable = false,
  onRemove,
  testID,
}: {
  agent: AgentId;
  tone?: AgentChipTone;
  size?: AgentChipSize;
  removable?: boolean;
  onRemove?: () => void;
  testID?: string;
}) {
  const { colors, typography } = useTheme();
  const iconSize = size === 'md' ? 20 : 16;
  const fontSize = size === 'md' ? 14 : 12;
  const horizontalPadding = size === 'md' ? 9 : 7;

  let bg: string;
  let fg: string;
  if (tone === 'on-user-bubble') {
    bg = 'rgba(0,0,0,0.18)';
    fg = colors.accentInk;
  } else {
    bg = agentTint(agent);
    fg = agentSolid(agent);
  }

  return (
    <View
      testID={testID}
      style={[
        styles.chip,
        {
          backgroundColor: bg,
          paddingLeft: 4,
          paddingRight: removable ? 4 : horizontalPadding,
        },
      ]}
    >
      <AgentMark agent={agent} size={iconSize} withBackground={false} />
      <Text style={[typography.bodyEm, { color: fg, fontSize, marginLeft: 5 }]}>
        {agent}
      </Text>
      {removable && (
        <Pressable
          testID="agent-chip-remove"
          onPress={onRemove}
          hitSlop={6}
          style={{ marginLeft: 4, paddingHorizontal: 4 }}
        >
          <Text style={{ color: fg, fontSize: 14, lineHeight: 14 }}>×</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: 12,
    paddingVertical: 2,
    alignSelf: 'flex-start',
  },
});
