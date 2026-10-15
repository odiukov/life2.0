import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { MAX_OFFSET } from './useDayFeed';

export function DaySwitcher({
  offset,
  today,
  onChange,
}: {
  offset: number;
  today: Date;
  onChange: (offset: number) => void;
}) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  const label =
    offset === 0
      ? t('me.today')
      : offset === 1
        ? t('me.yesterday')
        : new Date(
            today.getFullYear(),
            today.getMonth(),
            today.getDate() - offset,
          ).toLocaleDateString(appLocale(), { weekday: 'short', day: 'numeric', month: 'short' });
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t('me.prev_day')}
        disabled={offset >= MAX_OFFSET}
        onPress={() => onChange(offset + 1)}
        style={{ padding: 12, opacity: offset >= MAX_OFFSET ? 0.3 : 1 }}
      >
        <Text style={{ color: colors.fg1 }}>‹</Text>
      </Pressable>
      <Text style={{ color: colors.fg1 }}>{label}</Text>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={t('me.next_day')}
        disabled={offset === 0}
        onPress={() => onChange(offset - 1)}
        style={{ padding: 12, opacity: offset === 0 ? 0.3 : 1 }}
      >
        <Text style={{ color: colors.fg1 }}>›</Text>
      </Pressable>
    </View>
  );
}
