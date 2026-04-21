import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { Card, Screen, useTheme } from '@life-agents/ui';
import { useIntegrationsStore, isConnected, type IntegrationId, type IntegrationStatus } from '@/features/integrations/store';

const sources: readonly { id: IntegrationId; label: string }[] = [
  { id: 'apple-health', label: 'Apple Health' },
  { id: 'garmin',       label: 'Garmin' },
  { id: 'strava',       label: 'Strava' },
  { id: 'calendar',     label: 'Google Calendar' },
  { id: 'ha',           label: 'Home Assistant' },
  { id: 'payoneer',     label: 'Payoneer' },
  { id: 'yazio',        label: 'Yazio' },
] as const;

function labelFor(status: IntegrationStatus): string {
  return status.replace('-', ' ');
}

export function IntegrationsScreen() {
  const status = useIntegrationsStore((s) => s.status);
  const toggle = useIntegrationsStore((s) => s.toggle);
  const { colors, spacing, typography } = useTheme();

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: spacing.s3, gap: spacing.s2 }}>
        <Text style={[typography.caption, { color: colors.fg2, marginBottom: spacing.s2 }]}>
          Tap a row to toggle connected / not-connected in dev mode.
        </Text>
        {sources.map((s) => {
          const st = status[s.id];
          const connected = isConnected(st);
          return (
            <Pressable key={s.id} onPress={() => toggle(s.id)}>
              <Card>
                <View style={[styles.row, { gap: spacing.s3 }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{s.label}</Text>
                    <Text style={[typography.caption, { color: colors.fg2 }]}>{labelFor(st)}</Text>
                  </View>
                  <View
                    style={{
                      width: 10,
                      height: 10,
                      borderRadius: 5,
                      backgroundColor: connected ? colors.success : colors.fg3,
                    }}
                  />
                </View>
              </Card>
            </Pressable>
          );
        })}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { alignItems: 'center', flexDirection: 'row' },
});
