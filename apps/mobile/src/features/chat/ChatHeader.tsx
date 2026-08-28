// apps/mobile/src/features/chat/ChatHeader.tsx
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Icon, useTheme } from '@life-agents/ui';
import { useAgentStatusRows } from '@/features/agents/useAgentStatusRows';
import { formatRelativeTime } from '@/lib/formatRelativeTime';

export function ChatHeader() {
  const { colors, typography } = useTheme();
  const router = useRouter();
  const { readyCount, totalCount, lastSyncedAt, isSyncing, isLoading } = useAgentStatusRows();

  const dotColor = (() => {
    if (isLoading) return colors.fg3;
    const pct = totalCount === 0 ? 0 : readyCount / totalCount;
    if (pct >= 0.8) return colors.success;
    if (pct >= 0.4) return colors.warn;
    return colors.fg3;
  })();

  const subtitle = (() => {
    if (isLoading) return 'loading…';
    const time = isSyncing ? 'syncing…' : formatRelativeTime(lastSyncedAt);
    return `${readyCount}/${totalCount} ready · ${time}`;
  })();

  return (
    <Pressable
      onPress={() => router.push('/(tabs)')}
      accessibilityRole="button"
      accessibilityLabel={`Agent status, ${readyCount} of ${totalCount} ready. Tap to view agents on Home tab.`}
      style={[styles.bar, { borderBottomColor: colors.borderSoft, backgroundColor: colors.bg1 }]}
    >
      <View style={[styles.statusDot, { backgroundColor: colors.bg2, borderColor: colors.border }]}>
        <View style={[styles.innerDot, { backgroundColor: dotColor }]} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[typography.bodyEm, { color: colors.fg1 }]}>Life Agents</Text>
        <Text style={[typography.caption, { color: colors.fg3 }]}>{subtitle}</Text>
      </View>
      <Icon name="CaretRight" size={16} color={colors.fg3} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 12,
    paddingBottom: 14,
    borderBottomWidth: 1,
  },
  statusDot: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  innerDot: { width: 8, height: 8, borderRadius: 4 },
});
