import React from 'react';
import { View } from 'react-native';
import { agentIcons } from '../../icons/agents';
import type { AgentId } from '../AgentBadge';
import { useTheme } from '../../theme';

export function AgentMark({
  agent,
  size = 20,
  color,
  testID,
}: {
  agent: AgentId;
  size?: 16 | 20 | 24;
  color?: string;
  testID?: string;
}) {
  const { colors } = useTheme();
  const Icon = agentIcons[agent];
  return (
    <View testID={testID} style={{ width: size, height: size }}>
      <Icon width={size} height={size} color={color ?? colors.fg1} />
    </View>
  );
}
