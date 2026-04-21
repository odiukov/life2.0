import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { AgentMark, Card, Screen, useTheme } from '@life-agents/ui';

const logActions = [
  { id: 'meal',    label: 'Meal photo',    hint: 'Snap + LLM parse',     agent: 'nutrition'  as const },
  { id: 'workout', label: 'Voice workout', hint: 'Speak it, we log',     agent: 'workout'    as const },
  { id: 'mood',    label: 'Voice mood',    hint: "How's today feeling?", agent: 'mood'       as const },
  { id: 'habit',   label: 'Habit check',   hint: 'Mark today done',      agent: 'habits'     as const },
  { id: 'med',     label: 'Take meds',     hint: 'Log taken dose',       agent: 'medication' as const },
  { id: 'water',   label: 'Water',         hint: '+1 glass',             agent: 'nutrition'  as const },
];

export function QuickLogSheet() {
  const router = useRouter();
  const { spacing, colors, typography } = useTheme();

  const dismiss = () => {
    if (router.canGoBack()) router.back();
    else router.replace('/(tabs)/chat');
  };

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ paddingBottom: spacing.s6 }}>
        <Text
          style={[
            typography.micro,
            {
              color: colors.fg2,
              paddingHorizontal: spacing.s3,
              marginTop: spacing.s3,
              marginBottom: spacing.s2,
            },
          ]}
        >
          Log
        </Text>
        <View style={[styles.grid, { paddingHorizontal: spacing.s3, gap: spacing.s3 }]}>
          {logActions.map((a) => (
            <Pressable
              key={a.id}
              style={[styles.cell, { flexBasis: '47%' }]}
              onPress={dismiss}
            >
              <Card>
                <View style={{ alignItems: 'center', gap: spacing.s2, padding: spacing.s3 }}>
                  <AgentMark agent={a.agent} size={24} color={colors.accentHi} />
                  <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{a.label}</Text>
                  <Text style={[typography.caption, { color: colors.fg2, textAlign: 'center' }]}>
                    {a.hint}
                  </Text>
                </View>
              </Card>
            </Pressable>
          ))}
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap' },
  cell: { flexGrow: 1 },
});
