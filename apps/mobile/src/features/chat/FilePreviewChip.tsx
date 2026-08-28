import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@life-agents/ui';

export function FilePreviewChip({
  fileName,
  onDismiss,
}: {
  fileName: string;
  onDismiss: () => void;
}) {
  const { colors, radius, spacing, typography } = useTheme();
  return (
    <View
      style={[
        styles.chip,
        {
          backgroundColor: colors.bg2,
          borderRadius: radius.rMd,
          marginHorizontal: spacing.s3,
          marginBottom: spacing.s1,
          padding: spacing.s2,
        },
      ]}
    >
      <View style={[styles.badge, { backgroundColor: '#cc3333', borderRadius: 4 }]}>
        <Text style={styles.badgeText}>PDF</Text>
      </View>
      <Text
        style={[typography.caption, { color: colors.fg1, flex: 1 }]}
        numberOfLines={1}
        ellipsizeMode="middle"
      >
        {fileName}
      </Text>
      <Pressable testID="file-chip-dismiss" onPress={onDismiss} hitSlop={8}>
        <Text style={{ color: colors.fg3, fontSize: 16 }}>✕</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  badge: {
    width: 32,
    height: 38,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  badgeText: { color: '#fff', fontSize: 9, fontWeight: '700' },
});
