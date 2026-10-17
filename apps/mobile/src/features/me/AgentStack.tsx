import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { Icon, useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';

// Mirrors gateway ATTENTION_AGENTS: every agent the attention fan-out asks.
export const AGENT_TOTAL = 9;

export function AgentStack({ online, onPress }: { online: number | null; onPress: () => void }) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  const tint = online === null ? colors.fg3 : online === AGENT_TOTAL ? colors.success : colors.warn;
  const label =
    online === null
      ? t('me.all_agents')
      : `${t('me.all_agents')}, ${t('me.agents_online', { online, total: AGENT_TOTAL })}`;
  return (
    <Pressable
      testID="agent-stack"
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      style={[styles.pill, { backgroundColor: colors.bg2, borderColor: colors.border }]}
    >
      <Icon name="SquaresFour" size={17} color={colors.fg2} />
      {online !== null &&
        (online === AGENT_TOTAL ? (
          <View style={[styles.dot, { backgroundColor: tint, borderColor: colors.bg0 }]} />
        ) : (
          <View style={[styles.badge, { backgroundColor: tint }]}>
            <Text style={[styles.text, { color: colors.accentInk }]}>
              {online}/{AGENT_TOTAL}
            </Text>
          </View>
        ))}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  badge: {
    alignItems: 'center',
    borderRadius: 8,
    height: 16,
    justifyContent: 'center',
    paddingHorizontal: 4,
    position: 'absolute',
    right: -6,
    top: -4,
  },
  dot: {
    borderRadius: 6,
    borderWidth: 2,
    height: 12,
    position: 'absolute',
    right: -1,
    top: -1,
    width: 12,
  },
  pill: {
    alignItems: 'center',
    borderRadius: 19,
    borderWidth: 1,
    height: 38,
    justifyContent: 'center',
    marginRight: 8,
    width: 38,
  },
  text: { fontSize: 10, fontVariant: ['tabular-nums'], fontWeight: '700' },
});
