import React from 'react';
import { Text } from 'react-native';
import { useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
export function UnavailableNote({ agents }: { agents: AgentId[] }) {
  const t = useT(appLocale());
  const { colors, typography, spacing } = useTheme();
  if (!agents.length) return null;
  return (
    <Text
      testID="home-unavailable"
      style={[typography.caption, { color: colors.fg3, marginVertical: spacing.s2 }]}
    >
      {t('dashboard.unavailable', {
        agents: agents.map((a) => t(`dashboard.agent_labels.${a}`)).join(', '),
        count: agents.length,
      })}
    </Text>
  );
}
