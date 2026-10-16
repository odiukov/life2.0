import React from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import { agentSolid, useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';

const HEADS: AgentId[] = ['sleep', 'workout', 'nutrition', 'mood'];

export function AgentStack({ onPress }: { onPress: () => void }) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  return (
    <Pressable
      testID="agent-stack"
      accessibilityRole="button"
      accessibilityLabel={t('me.all_agents')}
      onPress={onPress}
      hitSlop={8}
      style={styles.row}
    >
      {HEADS.map((id, i) => (
        <View
          key={id}
          style={[
            styles.dot,
            { backgroundColor: agentSolid(id), borderColor: colors.bg0, marginLeft: i ? -7 : 0 },
          ]}
        />
      ))}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  dot: { borderRadius: 11, borderWidth: 2, height: 22, width: 22 },
  row: { alignItems: 'center', flexDirection: 'row', marginRight: 10 },
});
