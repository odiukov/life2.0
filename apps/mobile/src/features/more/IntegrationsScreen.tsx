import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { Card, Screen, useTheme } from '@life-agents/ui';

const sources = [
  { id: 'apple-health', label: 'Apple Health',    status: 'not-connected' },
  { id: 'garmin',       label: 'Garmin',          status: 'not-connected' },
  { id: 'strava',       label: 'Strava',          status: 'not-connected' },
  { id: 'calendar',     label: 'Google Calendar', status: 'not-connected' },
  { id: 'ha',           label: 'Home Assistant',  status: 'not-connected' },
  { id: 'payoneer',     label: 'Payoneer',        status: 'manual-upload' },
  { id: 'yazio',        label: 'Yazio',           status: 'device-only' },
] as const;

export function IntegrationsScreen() {
  const { colors, spacing, typography } = useTheme();
  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: spacing.s3, gap: spacing.s2 }}>
        {sources.map((s) => (
          <Card key={s.id}>
            <View style={[styles.row, { gap: spacing.s3 }]}>
              <View style={{ flex: 1 }}>
                <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{s.label}</Text>
                <Text style={[typography.caption, { color: colors.fg2 }]}>{s.status}</Text>
              </View>
              <View style={{
                width: 8,
                height: 8,
                borderRadius: 4,
                backgroundColor: s.status === 'not-connected' ? colors.fg3 : colors.success,
              }} />
            </View>
          </Card>
        ))}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({ row: { flexDirection: 'row', alignItems: 'center' } });
