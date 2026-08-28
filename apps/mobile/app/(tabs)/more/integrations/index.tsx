import React, { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { Card, Screen, useTheme } from '@life-agents/ui';
import { agentSolid } from '@life-agents/ui';
import {
  hydrateIntegrationsFromSecureStore,
  isConnected,
  useIntegrationsStore,
  type IntegrationId,
} from '@/features/integrations/store';

const PRIMARY_INTEGRATIONS = [
  {
    id: 'apple-health',
    storeId: 'apple-health',
    route: '/(tabs)/more/integrations/apple-health',
    label: 'Apple Health',
    brand: 'HK',
    description:
      'Sleep, HRV, workouts, steps, nutrition — feeds in from Garmin, Yazio, Apple Watch',
    agentHint: 'sleep',
  },
  {
    id: 'ha',
    storeId: 'ha',
    route: '/(tabs)/more/integrations/ha',
    label: 'Home Assistant',
    brand: 'HA',
    description: 'Connect your smart home hub',
    agentHint: 'home',
  },
  {
    id: 'google-calendar',
    storeId: 'calendar',
    route: '/(tabs)/more/integrations/google-calendar',
    label: 'Google Calendar',
    brand: 'GC',
    description: 'Sync your calendar events',
    agentHint: 'calendar',
  },
  {
    id: 'payoneer',
    storeId: 'payoneer',
    route: null,
    label: 'Payoneer',
    brand: 'PY',
    description: 'Income & spending feed — coming soon',
    agentHint: 'finance',
  },
] as const satisfies ReadonlyArray<{
  id: string;
  storeId: IntegrationId;
  route: string | null;
  label: string;
  brand: string;
  description: string;
  agentHint: string;
}>;

const ADVANCED_INTEGRATIONS = [
  {
    id: 'garmin',
    storeId: 'garmin',
    route: '/(tabs)/more/integrations/garmin',
    label: 'Garmin Connect',
    brand: 'GC',
    description:
      "Body Battery, Stress, Training Status — metrics that don't export to Apple Health",
    agentHint: 'workout',
  },
  {
    id: 'yazio',
    storeId: 'yazio',
    route: '/(tabs)/more/integrations/yazio',
    label: 'Yazio',
    brand: 'YZ',
    description: 'Food names, brands, serving info — Apple Health carries macro numbers only',
    agentHint: 'nutrition',
  },
] as const satisfies ReadonlyArray<{
  id: string;
  storeId: IntegrationId;
  route: string | null;
  label: string;
  brand: string;
  description: string;
  agentHint: string;
}>;

export default function IntegrationsIndexScreen() {
  const router = useRouter();
  const { colors, spacing, typography } = useTheme();
  const status = useIntegrationsStore((s) => s.status);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  // Re-hydrate from SecureStore on every focus as a safety net — covers the
  // case where a panel mutates the store outside this screen, the app was
  // backgrounded, or the in-memory store drifted from disk.
  useFocusEffect(
    useCallback(() => {
      hydrateIntegrationsFromSecureStore().catch(() => {});
    }, []),
  );

  function renderRow(
    it: (typeof PRIMARY_INTEGRATIONS)[number] | (typeof ADVANCED_INTEGRATIONS)[number],
  ) {
    const connected = isConnected(status[it.storeId]);
    const chipColor = connected ? agentSolid(it.agentHint as any) : colors.fg3;
    const chipBg = connected ? agentSolid(it.agentHint as any) + '22' : colors.bg3;
    return (
      <Pressable
        key={it.id}
        onPress={() => it.route && router.push(it.route as never)}
        disabled={!it.route}
      >
        <Card>
          <View style={styles.row}>
            <View
              style={[styles.brandChip, { backgroundColor: chipBg, borderColor: colors.border }]}
            >
              <Text style={{ color: chipColor, fontSize: 11, fontWeight: '700' }}>{it.brand}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{it.label}</Text>
                {connected && (
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                    <View style={[styles.connDot, { backgroundColor: colors.success }]} />
                    <Text style={{ fontSize: 10.5, color: colors.success, fontWeight: '600' }}>
                      Connected
                    </Text>
                  </View>
                )}
              </View>
              <Text style={[typography.caption, { color: colors.fg3, marginTop: 2 }]}>
                {connected ? `Synced 2 min ago · ${it.description}` : it.description}
              </Text>
            </View>
            <Text style={{ color: colors.fg4, fontSize: 16 }}>{it.route ? '›' : ''}</Text>
          </View>
        </Card>
      </Pressable>
    );
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: spacing.s4, gap: spacing.s4 }}>
        <Text style={[typography.display, { color: colors.fg1 }]}>Integrations</Text>
        <Text style={[typography.body, { color: colors.fg3, marginTop: -spacing.s2 }]}>
          Life Agents works with what you already use. Connect a source and the right agent will
          start referencing it.
        </Text>

        <View style={{ gap: spacing.s2 }}>{PRIMARY_INTEGRATIONS.map(renderRow)}</View>

        <Pressable
          testID="advanced-toggle"
          onPress={() => setAdvancedOpen((v) => !v)}
          accessibilityRole="button"
          accessibilityState={{ expanded: advancedOpen }}
          accessibilityLabel="Advanced sources"
          style={{
            marginTop: spacing.s2,
            paddingVertical: spacing.s2,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <Text style={[typography.bodyEm, { color: colors.fg2 }]}>Advanced sources</Text>
          <Text style={{ color: colors.fg3, fontSize: 14 }}>{advancedOpen ? '▾' : '▸'}</Text>
        </Pressable>

        {advancedOpen && (
          <>
            <Text style={[typography.caption, { color: colors.fg3, marginTop: -spacing.s1 }]}>
              Only needed if your Garmin or Yazio app isn’t sharing to Apple Health, or you want
              Garmin metrics that don’t export — Body Battery, Stress, Training Status.
            </Text>
            <View style={{ gap: spacing.s2 }}>{ADVANCED_INTEGRATIONS.map(renderRow)}</View>
          </>
        )}

        {/* Privacy note */}
        <View style={[styles.privacyNote, { borderColor: colors.border }]}>
          <Text style={[typography.caption, { color: colors.fg3, lineHeight: 18 }]}>
            All tokens are stored in the device secure enclave. Nothing leaves your phone unless an
            agent needs it to answer you.
          </Text>
        </View>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  brandChip: {
    width: 36,
    height: 36,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
  },
  connDot: { width: 6, height: 6, borderRadius: 3 },
  privacyNote: { padding: 14, borderRadius: 16, borderWidth: 1, borderStyle: 'dashed' },
});
