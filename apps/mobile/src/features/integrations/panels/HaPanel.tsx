import React, { useEffect, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import * as SecureStore from 'expo-secure-store';
import { Card, useTheme } from '@life-agents/ui';
import { apiBaseUrl } from '@/api/client';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';

const HA_KEY = 'ha_connected';

type Props = {
  onConnected?: () => void;
  onDisconnected?: () => void;
  onScroll?: React.ComponentProps<typeof KeyboardAwareScrollView>['onScroll'];
  scrollEventThrottle?: number;
};

export function HaPanel({ onConnected, onDisconnected, onScroll, scrollEventThrottle }: Props) {
  const { colors, spacing, typography, radius } = useTheme();
  const [baseUrl, setBaseUrl] = useState('');
  const [token, setToken] = useState('');
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync(HA_KEY).then((v) => {
      if (v) setConnected(true);
    });
  }, []);

  async function handleConnect() {
    if (!baseUrl.trim() || !token.trim()) {
      Alert.alert('Missing fields', 'Please enter both Base URL and Long-Lived Token.');
      return;
    }
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBaseUrl}/integrations/ha/connect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ base_url: baseUrl.trim(), token: token.trim() }),
      });
      if (res.ok) {
        await SecureStore.setItemAsync(HA_KEY, '1');
        setConnected(true);
        onConnected?.();
        Alert.alert('Connected', 'Home Assistant connected successfully.');
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

  async function handleTest() {
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBaseUrl}/integrations/ha/test`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
      });
      if (res.ok) {
        Alert.alert('Success', 'Home Assistant connection is working.');
      } else {
        Alert.alert('Failed', 'Could not reach Home Assistant. Check your settings.');
      }
    } catch {
      Alert.alert('Error', 'Network error.');
    } finally {
      setLoading(false);
    }
  }

  async function handleDisconnect() {
    setLoading(true);
    try {
      const headers = await getAuthHeaders();
      const res = await fetch(`${apiBaseUrl}/integrations/ha/disconnect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
      });
      if (res.ok) {
        await SecureStore.deleteItemAsync(HA_KEY);
        setConnected(false);
        setBaseUrl('');
        setToken('');
        onDisconnected?.();
        Alert.alert('Disconnected', 'Home Assistant has been disconnected.');
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

  const btnStyle = (variant: 'primary' | 'danger' | 'secondary') => [
    styles.btn,
    {
      backgroundColor:
        variant === 'primary' ? colors.accent : variant === 'danger' ? colors.danger : colors.bg2,
      borderRadius: radius.rMd,
      padding: spacing.s3,
      opacity: loading ? 0.6 : 1,
    },
  ];

  return (
    <KeyboardAwareScrollView
      testID="ha-scroll"
      onScroll={onScroll}
      scrollEventThrottle={scrollEventThrottle}
      contentContainerStyle={{ padding: spacing.s3, gap: spacing.s3 }}
      bottomOffset={spacing.s4}
      keyboardShouldPersistTaps="handled"
    >
      <Card>
        <Text style={[typography.bodyEm, { color: colors.fg1, marginBottom: spacing.s2 }]}>
          Home Assistant
        </Text>
        <Text style={[typography.caption, { color: colors.fg2, marginBottom: spacing.s3 }]}>
          Enter your Home Assistant URL and a Long-Lived Access Token.
        </Text>

        <Text style={[typography.caption, { color: colors.fg2, marginBottom: spacing.s1 }]}>
          Base URL
        </Text>
        <TextInput
          testID="ha-base-url-input"
          style={inputStyle}
          value={baseUrl}
          onChangeText={setBaseUrl}
          placeholder="http://homeassistant.local:8123"
          placeholderTextColor={colors.fg3}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          editable={!connected}
        />

        <Text
          style={[
            typography.caption,
            { color: colors.fg2, marginBottom: spacing.s1, marginTop: spacing.s2 },
          ]}
        >
          Long-Lived Access Token
        </Text>
        <TextInput
          testID="ha-token-input"
          style={inputStyle}
          value={token}
          onChangeText={setToken}
          placeholder="eyJ0eXAi..."
          placeholderTextColor={colors.fg3}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
          editable={!connected}
        />
      </Card>

      <View style={{ gap: spacing.s2 }}>
        {!connected && (
          <Pressable
            testID="ha-connect"
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
            testID="ha-test"
            onPress={handleTest}
            disabled={loading}
            style={btnStyle('secondary')}
          >
            <Text style={[typography.bodyEm, { color: colors.fg1, textAlign: 'center' }]}>
              {loading ? 'Testing…' : 'Test connection'}
            </Text>
          </Pressable>
        )}
        {connected && (
          <Pressable
            testID="ha-disconnect"
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
