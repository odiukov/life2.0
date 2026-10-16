import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { AttentionCard } from './AttentionCard';
import type { AttentionItem } from './useAttention';

function Separator({ label }: { label: string }) {
  const { colors } = useTheme();
  return (
    <View style={styles.sep}>
      <Text style={{ color: colors.fg3, fontSize: 11 }}>{label}</Text>
      <View style={[styles.line, { backgroundColor: colors.borderSoft }]} />
    </View>
  );
}

export function AttentionList({
  items,
  onOpen,
  onDismiss,
}: {
  items: AttentionItem[];
  onOpen: (item: AttentionItem) => void;
  onDismiss: (id: string) => void;
}) {
  const t = useT(appLocale());
  if (items.length === 0) return null;
  return (
    <View style={{ gap: 6 }}>
      <Separator label={t('attention.now')} />
      {items.map((item) => (
        <AttentionCard key={item.id} item={item} onPress={onOpen} onDismiss={onDismiss} />
      ))}
      <Separator label={t('attention.earlier')} />
    </View>
  );
}

const styles = StyleSheet.create({
  line: { flex: 1, height: StyleSheet.hairlineWidth },
  sep: { alignItems: 'center', flexDirection: 'row', gap: 6, marginTop: 4 },
});
