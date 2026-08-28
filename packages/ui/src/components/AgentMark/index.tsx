import React from 'react';
import { View } from 'react-native';
import { agentIcons } from '../../icons/agents';
import type { AgentId } from '../AgentBadge';
import { agentSolid, agentTint } from '../../tokens/agentColors';

export function AgentMark({
  agent,
  size = 24,
  withBackground = true,
  testID,
}: {
  agent: AgentId | string;
  size?: number;
  withBackground?: boolean;
  color?: string; // kept for back-compat, ignored when withBackground=true
  testID?: string;
}) {
  const Icon = agentIcons[agent as AgentId] ?? agentIcons.home;
  const iconSize = Math.round(size * 0.58);
  const solid = agentSolid(agent);
  const tint = agentTint(agent);

  if (!withBackground) {
    return (
      <View
        testID={testID}
        style={{
          width: size,
          height: size,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Icon width={iconSize} height={iconSize} color={solid} />
      </View>
    );
  }

  return (
    <View
      testID={testID}
      style={{
        width: size,
        height: size,
        borderRadius: size / 2,
        backgroundColor: tint,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Icon width={iconSize} height={iconSize} color={solid} />
    </View>
  );
}
