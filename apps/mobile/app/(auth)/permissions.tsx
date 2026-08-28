import React, { useEffect, useState } from 'react';
import { Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Screen, useTheme } from '@life-agents/ui';
import { requestPermissions } from '@/features/healthkit/permissions';
import { runSync } from '@/features/healthkit/sync';

export default function PermissionsScreen() {
  const router = useRouter();
  const { colors, spacing, typography } = useTheme();
  const [status, setStatus] = useState<'requesting' | 'syncing' | 'done'>('requesting');
  const [uploaded, setUploaded] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function run() {
      // 1. Request HealthKit permissions (no-op on non-iOS / Expo Go)
      await requestPermissions();
      if (cancelled) return;

      setStatus('syncing');

      // 2. Initial sync
      try {
        const result = await runSync();
        if (!cancelled) setUploaded(result.uploaded);
      } catch (err) {
        // Non-fatal — user can sync later via background task
        console.warn('[PermissionsScreen] sync error:', err);
      }

      if (cancelled) return;
      setStatus('done');

      // Navigate to main app
      router.replace('/(tabs)/chat');
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const label =
    status === 'requesting'
      ? 'Requesting permissions…'
      : status === 'syncing'
        ? `Syncing${uploaded > 0 ? ` ${uploaded} records` : ''}…`
        : 'Done!';

  return (
    <Screen testID="permissions-screen">
      <View
        style={{ flex: 1, justifyContent: 'center', alignItems: 'center', padding: spacing.s6 }}
      >
        <Text
          style={[
            typography.title1,
            { color: colors.fg1, textAlign: 'center', marginBottom: spacing.s4 },
          ]}
        >
          Setting up…
        </Text>
        <Text
          style={[
            typography.body,
            { color: colors.fg2, textAlign: 'center', marginBottom: spacing.s4 },
          ]}
        >
          Apple Health is how Life Agents picks up data from Garmin, Yazio, your Apple Watch, and
          your iPhone. You can connect those services directly later if you need metrics Apple
          Health doesn’t carry.
        </Text>
        <Text style={[typography.body, { color: colors.fg2, textAlign: 'center' }]}>{label}</Text>
      </View>
    </Screen>
  );
}
