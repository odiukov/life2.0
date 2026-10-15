import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { AgentMark, Icon, agentSolid, useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';

export function LeadChip({ agent, onClear }: { agent: AgentId; onClear: () => void }) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 6,
        paddingVertical: 4,
        paddingLeft: 8,
        paddingRight: 4,
        borderRadius: 999,
        borderWidth: 1,
        borderColor: agentSolid(agent),
        backgroundColor: colors.bg2,
      }}
    >
      <AgentMark agent={agent} size={14} />
      <Text style={{ color: colors.fg1, fontSize: 12.5, fontWeight: '600' }}>
        {t(`dashboard.agent_labels.${agent}`)}
      </Text>
      <Pressable
        onPress={onClear}
        hitSlop={8}
        accessibilityRole="button"
        accessibilityLabel={t('task.lead_remove')}
      >
        <Icon name="X" size={12} color={colors.fg3} />
      </Pressable>
    </View>
  );
}
