import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import { Card, useTheme } from '@life-agents/ui';
import { requestPermissions } from '@/features/healthkit/permissions';
import { runSync, getDetectedSources } from '@/features/healthkit/sync';

const LAST_SYNC_KEY = 'hk_last_sync';

type Props = {
  onConnected?: () => void;
  onDisconnected?: () => void;
};

export function AppleHealthPanel({ onConnected, onDisconnected }: Props) {
  const { colors, spacing, typography } = useTheme();
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [loading, setLoading] = useState<'perm' | 'sync' | null>(null);
  const [sources, setSources] = useState<string[]>([]);
  const connected = lastSync !== null;

  useEffect(() => {
    SecureStore.getItemAsync(LAST_SYNC_KEY).then(setLastSync);
  }, []);

  useEffect(() => {
    getDetectedSources().then(setSources);
  }, [lastSync]);

  async function handleGrant() {
    setLoading('perm');
    let granted = false;
    try {
      granted = await requestPermissions();
    } finally {
      setLoading(null);
    }
    if (!granted) {
      Alert.alert(
        'Permissions not granted',
        'Open Settings → Privacy & Security → Health → Life Agents to enable access.',
      );
      return;
    }
    await handleSync();
  }

  async function handleDisconnect() {
    Alert.alert(
      'Disconnect Apple Health?',
      'This will stop Life Agents from syncing new HealthKit data on this device. Previously synced data stays on your account. To fully revoke HealthKit access, go to iOS Settings → Privacy & Security → Health → Life Agents.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: async () => {
            await SecureStore.deleteItemAsync(LAST_SYNC_KEY);
            setLastSync(null);
            onDisconnected?.();
          },
        },
      ],
    );
  }

  async function handleSync() {
    setLoading('sync');
    try {
      await requestPermissions();
      const result = await runSync({ force: true });
      const fresh = await SecureStore.getItemAsync(LAST_SYNC_KEY);
      setLastSync(fresh);
      if (!connected) onConnected?.();
      Alert.alert('Sync complete', `${result.uploaded} samples uploaded`);
    } catch (e) {
      Alert.alert('Sync failed', e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(null);
    }
  }

  return (
    <View style={[styles.container, { padding: spacing.s3, gap: spacing.s3 }]}>
      <Text style={[typography.display, { color: colors.fg1 }]}>Apple Health</Text>
      <Text style={[typography.body, { color: colors.fg2 }]}>
        Your sleep, heart rate variability, workouts, steps and nutrition flow from HealthKit on
        this device into your agents. Runs in the background every 30 min.
      </Text>

      <Card>
        <View style={[styles.statusRow, { gap: spacing.s2 }]}>
          <View
            style={[styles.dot, { backgroundColor: connected ? colors.success : colors.fg3 }]}
          />
          <View style={{ flex: 1 }}>
            <Text style={[typography.caption, { color: colors.fg2 }]}>
              {connected ? 'Connected — synced' : 'Not yet synced'}
            </Text>
            <Text style={[typography.body, { color: colors.fg1, marginTop: spacing.s1 }]}>
              {connected ? new Date(lastSync!).toLocaleString() : '—'}
            </Text>
          </View>
        </View>
      </Card>

      {sources.length > 0 && (
        <Card>
          <Text style={[typography.caption, { color: colors.fg2, marginBottom: spacing.s2 }]}>
            Detected sources
          </Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.s1 }}>
            {sources.map((s) => (
              <View
                key={s}
                style={{
                  backgroundColor: colors.bg2,
                  borderColor: colors.border,
                  borderWidth: 1,
                  borderRadius: 999,
                  paddingHorizontal: spacing.s2,
                  paddingVertical: 4,
                }}
              >
                <Text style={[typography.caption, { color: colors.fg1 }]}>{s}</Text>
              </View>
            ))}
          </View>
        </Card>
      )}

      {!connected && (
        <Pressable
          testID="hk-grant-permissions"
          onPress={handleGrant}
          disabled={loading !== null}
          style={[
            styles.button,
            { backgroundColor: colors.fg1, padding: spacing.s3 },
            loading !== null && styles.disabled,
          ]}
        >
          <Text style={[typography.body, styles.center, { color: colors.bg1 }]}>
            {loading === 'perm'
              ? 'Requesting permissions…'
              : loading === 'sync'
                ? 'Syncing…'
                : 'Connect Apple Health'}
          </Text>
        </Pressable>
      )}

      {connected && (
        <>
          <Pressable
            testID="hk-sync-now"
            onPress={handleSync}
            disabled={loading !== null}
            style={[
              styles.button,
              { backgroundColor: colors.bg3, padding: spacing.s3 },
              loading !== null && styles.disabled,
            ]}
          >
            <Text style={[typography.body, styles.center, { color: colors.fg2 }]}>
              {loading === 'sync' ? 'Syncing…' : 'Sync again'}
            </Text>
          </Pressable>

          <Pressable
            testID="hk-disconnect"
            onPress={handleDisconnect}
            disabled={loading !== null}
            style={[
              styles.button,
              { backgroundColor: colors.danger, padding: spacing.s3 },
              loading !== null && styles.disabled,
            ]}
          >
            <Text style={[typography.bodyEm, styles.center, { color: '#fff' }]}>Disconnect</Text>
          </Pressable>
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  button: { borderRadius: 12 },
  center: { textAlign: 'center' },
  disabled: { opacity: 0.5 },
  statusRow: { flexDirection: 'row', alignItems: 'center' },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
