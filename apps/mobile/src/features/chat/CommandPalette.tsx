import React from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';
import { AgentMark, useTheme } from '@life-agents/ui';
import type { ChatCommand } from './commands';

export function CommandPalette({
  items,
  onSelect,
}: {
  items: readonly ChatCommand[];
  onSelect: (c: ChatCommand) => void;
}) {
  const { colors, radius, spacing, typography } = useTheme();
  if (items.length === 0) return null;
  return (
    <View
      style={[
        styles.container,
        {
          backgroundColor: colors.bg1,
          borderColor: colors.border,
          borderRadius: radius.rLg,
          marginHorizontal: spacing.s3,
          maxHeight: 280,
        },
      ]}
    >
      <FlatList
        data={items as ChatCommand[]}
        keyboardShouldPersistTaps="always"
        keyExtractor={(c) => c.name}
        renderItem={({ item }) => (
          <Pressable
            onPress={() => onSelect(item)}
            style={{
              flexDirection: 'row',
              alignItems: 'center',
              paddingHorizontal: spacing.s3,
              paddingVertical: spacing.s3,
              gap: spacing.s3,
            }}
          >
            <AgentMark agent={item.agent} size={20} color={colors.accentHi} />
            <View style={{ flex: 1 }}>
              <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{item.name}</Text>
              <Text style={[typography.caption, { color: colors.fg2 }]}>{item.hint}</Text>
            </View>
          </Pressable>
        )}
        ItemSeparatorComponent={() => (
          <View style={{ height: 1, backgroundColor: colors.border, marginLeft: spacing.s8 }} />
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { borderWidth: 1, overflow: 'hidden' },
});
