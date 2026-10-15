import React, { useState } from 'react';
import { FlatList, Pressable, Text, View } from 'react-native';
import { router } from 'expo-router';
import { Screen, useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { useInbox, useInboxActions } from './useInbox';

export const NOTIFICATION_ROUTES: Record<string, string> = { '/kitchen': '/(tabs)/house' };

export function InboxScreen() {
  const { colors, spacing, typography } = useTheme();
  const t = useT(appLocale());
  const inbox = useInbox();
  const { read, readAll } = useInboxActions();
  const [actionError, setActionError] = useState(false);
  const open = async (item: NonNullable<typeof inbox.data>['items'][number]) => {
    setActionError(false);
    try {
      if (!item.read_at) await read.mutateAsync(item.id);
      const route = item.data.route ? NOTIFICATION_ROUTES[item.data.route] ?? item.data.route : null;
      if (route) router.push(route as never);
    } catch {
      setActionError(true);
    }
  };
  const markAll = async () => {
    setActionError(false);
    try {
      await readAll.mutateAsync();
    } catch {
      setActionError(true);
    }
  };

  return (
    <Screen edges={['top']}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: spacing.s4 }}>
        <Text style={[typography.display, { color: colors.fg1 }]}>{t('inbox.title')}</Text>
        {!!inbox.data?.unread_count && (
          <Pressable onPress={() => { void markAll(); }} accessibilityRole="button" disabled={readAll.isPending}>
            <Text style={{ color: colors.accentHi }}>{t('inbox.read_all')}</Text>
          </Pressable>
        )}
      </View>
      {actionError && <Text style={{ color: colors.danger, paddingHorizontal: spacing.s4 }}>{t('inbox.update_error')}</Text>}
      {inbox.isError && <Text style={{ color: colors.danger, paddingHorizontal: spacing.s4 }}>{t('inbox.load_error')}</Text>}
      <FlatList
        data={inbox.data?.items ?? []}
        keyExtractor={(item) => item.id}
        contentContainerStyle={{ padding: spacing.s4, gap: spacing.s2 }}
        ListEmptyComponent={!inbox.isPending && !inbox.isError ? <Text style={{ color: colors.fg3 }}>{t('inbox.empty')}</Text> : null}
        renderItem={({ item }) => (
          <Pressable onPress={() => { void open(item); }} disabled={read.isPending} accessibilityRole="button">
            <View style={{ padding: spacing.s3, borderRadius: 12, backgroundColor: item.read_at ? colors.bg1 : colors.bg2 }}>
              <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{item.title}</Text>
              <Text style={{ color: colors.fg3, marginTop: 2 }}>{item.body}</Text>
            </View>
          </Pressable>
        )}
      />
    </Screen>
  );
}
