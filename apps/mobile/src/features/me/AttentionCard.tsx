import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import ReanimatedSwipeable from 'react-native-gesture-handler/ReanimatedSwipeable';
import { AgentMark, useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import type { AttentionItem } from './useAttention';

type Props = {
  item: AttentionItem;
  onPress: (item: AttentionItem) => void;
  onDismiss: (id: string) => void;
};

export function AttentionCard({ item, onPress, onDismiss }: Props) {
  const { colors, radius } = useTheme();
  const t = useT(appLocale());
  const critical = item.level === 'critical';
  const tone =
    item.level === 'critical' ? colors.danger : item.level === 'high' ? colors.warn : colors.info;
  const soft =
    item.level === 'critical'
      ? colors.dangerSoft
      : item.level === 'high'
        ? colors.warnSoft
        : colors.infoSoft;
  const card = (
    <Pressable
      accessibilityRole="button"
      onPress={() => onPress(item)}
      style={[
        styles.card,
        {
          borderRadius: radius.rMd,
          backgroundColor: critical ? colors.dangerSoft : colors.bg2,
          borderColor: critical ? colors.danger : colors.borderSoft,
        },
      ]}
    >
      <View style={[styles.dot, { backgroundColor: soft }]}>
        <AgentMark agent={item.agent as AgentId} size={16} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={styles.titleRow}>
          <Text numberOfLines={1} style={[styles.title, { color: colors.fg1 }]}>
            {item.text}
          </Text>
          {critical && (
            <Text style={[styles.tag, { color: tone, backgroundColor: colors.dangerSoft }]}>
              {t('attention.urgent')}
            </Text>
          )}
        </View>
        {item.detail ? (
          <Text numberOfLines={1} style={[styles.detail, { color: colors.fg2 }]}>
            {item.detail}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
  if (critical) return card;
  return (
    <ReanimatedSwipeable
      testID="attention-swipe"
      friction={2}
      rightThreshold={40}
      renderRightActions={() => (
        <Pressable
          accessibilityRole="button"
          onPress={() => onDismiss(item.id)}
          style={[styles.hide, { backgroundColor: colors.bg3, borderRadius: radius.rMd }]}
        >
          <Text style={{ color: colors.fg2, fontSize: 11, textAlign: 'center' }}>
            {t('attention.hide')}
          </Text>
        </Pressable>
      )}
    >
      {card}
    </ReanimatedSwipeable>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, flexDirection: 'row', gap: 10, padding: 10 },
  detail: { fontSize: 12, marginTop: 2 },
  dot: { alignItems: 'center', borderRadius: 13, height: 26, justifyContent: 'center', width: 26 },
  hide: { alignItems: 'center', justifyContent: 'center', marginLeft: 6, width: 84 },
  tag: {
    borderRadius: 5,
    fontSize: 9.5,
    fontWeight: '700',
    overflow: 'hidden',
    paddingHorizontal: 5,
  },
  title: { flexShrink: 1, fontSize: 13, fontWeight: '600' },
  titleRow: { alignItems: 'center', flexDirection: 'row', gap: 6 },
});
