import React from 'react';
import { Pressable, ScrollView, Text } from 'react-native';
import { useRouter } from 'expo-router';
import { Card, Screen, useTheme } from '@life-agents/ui';

const rows = [
  { to: '/(tabs)/more/integrations', label: 'Integrations' },
  { to: '/(tabs)/more/tone', label: 'Voice & tone' },
  { to: '/(tabs)/more/privacy', label: 'Privacy & data' },
  { to: '/(tabs)/more/subscription', label: 'Subscription' },
  { to: '/(tabs)/more/about', label: 'About' },
];

export function MoreScreen() {
  const router = useRouter();
  const { colors, spacing, typography } = useTheme();
  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: spacing.s3, gap: spacing.s3 }}>
        {rows.map((r) => (
          <Pressable key={r.to} onPress={() => router.push(r.to as never)}>
            <Card>
              <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{r.label}</Text>
            </Card>
          </Pressable>
        ))}
      </ScrollView>
    </Screen>
  );
}
