import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import * as SecureStore from 'expo-secure-store';
import { Card, useTheme } from '@life-agents/ui';
import { apiBaseUrl } from '@/api/client';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';

const YAZIO_KEY = 'yazio_connected';
const YAZIO_EMAIL_KEY = 'yazio_email';

type Props = {
  onConnected?: () => void;
  onDisconnected?: () => void;
  onScroll?: React.ComponentProps<typeof KeyboardAwareScrollView>['onScroll'];
  scrollEventThrottle?: number;
};

export function YazioPanel({
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
    SecureStore.getItemAsync(YAZIO_KEY).then((v) => {
      if (v) setConnected(true);
    });
    SecureStore.getItemAsync(YAZIO_EMAIL_KEY).then((v) => {
      if (v) setEmail(v);
    });
  }, []);

  const [preflight, setPreflight] = useState<{ lastSeen: string | null } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const headers = await getAuthHeaders();
        const res = await fetch(`${apiBaseUrl}/integrations/preflight?service=yazio`, { headers });
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
      Alert.alert('Missing fields', 'Please enter your Yazio email and password.');
      return;
    }
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBaseUrl}/integrations/yazio/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      if (res.ok) {
        await SecureStore.setItemAsync(YAZIO_KEY, '1');
        await SecureStore.setItemAsync(YAZIO_EMAIL_KEY, email.trim());
        setConnected(true);
        setPassword('');
        onConnected?.();
        Alert.alert('Connected', 'Yazio connected successfully.');
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
      const res = await fetch(`${apiBaseUrl}/integrations/yazio/disconnect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
      });
      if (res.ok) {
        await SecureStore.deleteItemAsync(YAZIO_KEY);
        setConnected(false);
        setPassword('');
        onDisconnected?.();
        Alert.alert('Disconnected', 'Yazio has been disconnected.');
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
      testID="yazio-scroll"
      onScroll={onScroll}
      scrollEventThrottle={scrollEventThrottle}
      contentContainerStyle={{ padding: spacing.s3, gap: spacing.s3 }}
      bottomOffset={spacing.s4}
      keyboardShouldPersistTaps="handled"
    >
      <Card>
        {preflight && (
          <View
            testID="yazio-preflight-banner"
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
              We{'’'}re already receiving Yazio data via Apple Health
              {preflight.lastSeen
                ? ` (last sample: ${new Date(preflight.lastSeen).toLocaleString()})`
                : ''}
              . Connect direct credentials only if you need data Apple Health doesn{'’'}t carry —
              food names, brands, and serving info (Apple Health carries macro numbers only).
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
            Yazio credentials are stored encrypted on our server. Third-party risk — Yazio may block
            this access at any time.
          </Text>
        </View>

        <Text style={[typography.bodyEm, { color: colors.fg1, marginBottom: spacing.s3 }]}>
          Yazio Account
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
              testID="yazio-email-input"
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
              testID="yazio-password-input"
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
            testID="yazio-connect"
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
            testID="yazio-disconnect"
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
