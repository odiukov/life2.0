import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import * as SecureStore from 'expo-secure-store';
import { Card, useTheme } from '@life-agents/ui';
import { apiBaseUrl } from '@/api/client';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';

const GARMIN_KEY = 'garmin_connected';
const GARMIN_EMAIL_KEY = 'garmin_email';

type Props = {
  onConnected?: () => void;
  onDisconnected?: () => void;
  onScroll?: React.ComponentProps<typeof KeyboardAwareScrollView>['onScroll'];
  scrollEventThrottle?: number;
};

export function GarminPanel({
  onConnected,
  onDisconnected,
  onScroll,
  scrollEventThrottle,
}: Props) {
  const { colors, spacing, typography, radius } = useTheme();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync(GARMIN_KEY).then((v) => {
      if (v) setConnected(true);
    });
    SecureStore.getItemAsync(GARMIN_EMAIL_KEY).then((v) => {
      if (v) setEmail(v);
    });
  }, []);

  const [preflight, setPreflight] = useState<{ lastSeen: string | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const headers = await getAuthHeaders();
        const res = await fetch(`${apiBaseUrl}/integrations/preflight?service=garmin`, { headers });
        if (!res.ok) return;
        const body = await res.json();
        if (cancelled) return;
        if (body?.detected) {
          setPreflight({ lastSeen: body.last_seen ?? null });
        }
      } catch {
        // Network error — banner just doesn't appear; not user-visible.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleConnect() {
    if (!email.trim() || !password.trim()) {
      Alert.alert('Missing fields', 'Please enter your Garmin Connect email and password.');
      return;
    }
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBaseUrl}/integrations/garmin/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (res.ok) {
        await SecureStore.setItemAsync(GARMIN_KEY, '1');
        await SecureStore.setItemAsync(GARMIN_EMAIL_KEY, email.trim());
        setConnected(true);
        setPassword('');
        onConnected?.();
        Alert.alert('Connected', 'Garmin Connect synced successfully.');
      } else {
        const body = await res.json().catch(() => ({}));
        Alert.alert('Error', body?.detail ?? `Connection failed (${res.status}).`);
      }
    } catch {
      Alert.alert('Error', 'Network error. Check your connection.');
    } finally {
      setLoading(false);
    }
  }

  async function handleDisconnect() {
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBaseUrl}/integrations/garmin/disconnect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
      });
      if (res.ok) {
        await SecureStore.deleteItemAsync(GARMIN_KEY);
        setConnected(false);
        setPassword('');
        onDisconnected?.();
        Alert.alert('Disconnected', 'Garmin has been disconnected.');
      } else {
        Alert.alert('Error', 'Failed to disconnect.');
      }
    } catch {
      Alert.alert('Error', 'Network error.');
    } finally {
      setLoading(false);
    }
  }

  const inputStyle = [
    styles.input,
    {
      backgroundColor: colors.bg2,
      borderColor: colors.border,
      color: colors.fg1,
      borderRadius: radius.rMd,
      padding: spacing.s3,
    },
  ];

  const btnStyle = (variant: 'primary' | 'danger') => [
    styles.btn,
    {
      backgroundColor: variant === 'primary' ? colors.accent : colors.danger,
      borderRadius: radius.rMd,
      padding: spacing.s3,
      opacity: loading ? 0.6 : 1,
    },
  ];

  return (
    <KeyboardAwareScrollView
      testID="garmin-scroll"
      onScroll={onScroll}
      scrollEventThrottle={scrollEventThrottle}
      contentContainerStyle={{ padding: spacing.s3, gap: spacing.s3 }}
      bottomOffset={spacing.s4}
      keyboardShouldPersistTaps="handled"
    >
      <Card>
        {preflight && (
          <View
            testID="garmin-preflight-banner"
            style={{
              backgroundColor: colors.bg2,
              borderColor: colors.border,
              borderWidth: 1,
              borderRadius: radius.rMd,
              padding: spacing.s3,
              marginBottom: spacing.s3,
            }}
          >
            <Text style={[typography.caption, { color: colors.fg2 }]}>
              We{'’'}re already receiving Garmin data via Apple Health
              {preflight.lastSeen
                ? ` (last sample: ${new Date(preflight.lastSeen).toLocaleString()})`
                : ''}
              . Connect direct credentials only if you need data Apple Health doesn{'’'}t carry —
              Body Battery, Stress, Training Status, Recovery Time.
            </Text>
          </View>
        )}
        <View
          style={{
            backgroundColor: colors.bg2,
            borderColor: colors.border,
            borderWidth: 1,
            borderRadius: radius.rMd,
            padding: spacing.s3,
            marginBottom: spacing.s3,
          }}
        >
          <Text style={[typography.caption, { color: colors.fg2 }]}>
            {'⚠️ '}
            Garmin credentials are stored encrypted on our server. Garmin may block unofficial
            access at any time.
          </Text>
        </View>

        <Text style={[typography.bodyEm, { color: colors.fg1, marginBottom: spacing.s3 }]}>
          Garmin Connect Account
        </Text>

        {connected ? (
          <Text style={[typography.caption, { color: colors.fg2 }]}>
            Connected as <Text style={{ color: colors.fg1 }}>{email || '—'}</Text>
          </Text>
        ) : (
          <>
            <Text style={[typography.caption, { color: colors.fg2, marginBottom: spacing.s1 }]}>
              Email
            </Text>
            <TextInput
              testID="garmin-email-input"
              style={inputStyle}
              value={email}
              onChangeText={setEmail}
              placeholder="your@email.com"
              placeholderTextColor={colors.fg3}
              autoCapitalize="none"
              keyboardType="email-address"
            />

            <Text
              style={[
                typography.caption,
                { color: colors.fg2, marginBottom: spacing.s1, marginTop: spacing.s2 },
              ]}
            >
              Password
            </Text>
            <TextInput
              testID="garmin-password-input"
              style={inputStyle}
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••"
              placeholderTextColor={colors.fg3}
              secureTextEntry
            />
          </>
        )}
      </Card>

      <View style={{ gap: spacing.s2 }}>
        {!connected && (
          <Pressable
            testID="garmin-connect"
            onPress={handleConnect}
            disabled={loading}
            style={btnStyle('primary')}
          >
            <Text style={[typography.bodyEm, { color: '#fff', textAlign: 'center' }]}>
              {loading ? 'Connecting…' : 'Connect'}
            </Text>
          </Pressable>
        )}
        {connected && (
          <Pressable
            testID="garmin-disconnect"
            onPress={handleDisconnect}
            disabled={loading}
            style={btnStyle('danger')}
          >
            <Text style={[typography.bodyEm, { color: '#fff', textAlign: 'center' }]}>
              Disconnect
            </Text>
          </Pressable>
        )}
      </View>
    </KeyboardAwareScrollView>
  );
}

const styles = StyleSheet.create({
  input: { borderWidth: 1 },
  btn: { alignItems: 'center' },
});
