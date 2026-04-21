import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { AgentMark, Card, Screen, useTheme } from '@life-agents/ui';

const actions = [
  { id: 'meal',    label: 'Meal photo',    agent: 'nutrition'  as const },
  { id: 'workout', label: 'Voice workout', agent: 'workout'    as const },
  { id: 'mood',    label: 'Voice mood',    agent: 'mood'       as const },
  { id: 'habit',   label: 'Habit check',   agent: 'habits'     as const },
  { id: 'med',     label: 'Take meds',     agent: 'medication' as const },
  { id: 'water',   label: 'Water',         agent: 'nutrition'  as const },
];

export function QuickLogSheet() {
  const router = useRouter();
  const { spacing, colors, typography } = useTheme();
  return (
    <Screen>
      <View style={[styles.grid, { padding: spacing.s3, gap: spacing.s3 }]}>
        {actions.map((a) => (
          <Pressable
            key={a.id}
            style={[styles.cell, { flexBasis: '47%' }]}
            onPress={() => {
              // P3-a runtime will hook each into the right agent. For now, close.
              router.back();
            }}
          >
            <Card>
              <View style={{ alignItems: 'center', gap: spacing.s2, padding: spacing.s3 }}>
                <AgentMark agent={a.agent} size={24} color={colors.accentHi} />
                <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{a.label}</Text>
              </View>
            </Card>
          </Pressable>
        ))}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  grid: { flex: 1, flexDirection: 'row', flexWrap: 'wrap' },
  cell: { flexGrow: 1 },
});
