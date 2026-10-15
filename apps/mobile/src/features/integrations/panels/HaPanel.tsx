import React, { useEffect, useRef, useState } from 'react';
import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { KeyboardAwareScrollView } from 'react-native-keyboard-controller';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { useIntegrationsStore } from '../store';
import { Card, useTheme } from '@life-agents/ui';
import { gateway, errorCode } from '@/api/gateway';

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
  const t = useT(appLocale());
  const [status, setStatus] = useState<{
    connected: boolean;
    connected_by: string | null;
    connected_at: string | null;
  }>({ connected: false, connected_by: null, connected_at: null });
  const mounted = useRef(true);
  const connected = status.connected;
  const [loading, setLoading] = useState(true);

  async function refreshStatus() {
    const { data, error } = await gateway.GET('/integrations/ha/status');
    if (!mounted.current) return;
    if (error || !data) throw new Error(errorCode(error) ?? t('integrations.ha.status_failed'));
    setStatus({
      connected: data.connected,
      connected_by: data.connected_by ?? null,
      connected_at: data.connected_at ?? null,
    });
    useIntegrationsStore.getState().set('ha', data.connected ? 'connected' : 'not-connected');
  }

  useEffect(() => {
    mounted.current = true;
    void refreshStatus()
      .catch(() => {
        if (mounted.current) Alert.alert('Error', t('integrations.ha.status_failed'));
      })
      .finally(() => {
        if (mounted.current) setLoading(false);
      });
    return () => {
      mounted.current = false;
    };
  }, []);

  async function handleConnect() {
    if (!baseUrl.trim() || !token.trim()) {
      Alert.alert('Missing fields', 'Please enter both Base URL and Long-Lived Token.');
      return;
    }
    setLoading(true);
    try {
      const { error } = await gateway.POST('/integrations/ha/connect', {
        body: { base_url: baseUrl.trim(), token: token.trim() },
      });
      if (error) {
        Alert.alert('Error', errorCode(error) ?? t('chat.client.generic'));
        return;
      }
      await refreshStatus();
      setToken('');
      onConnected?.();
      Alert.alert('Connected', 'Home Assistant connected successfully.');
    } catch {
      Alert.alert('Error', 'Network error. Check your connection.');
    } finally {
      setLoading(false);
    }
  }

  async function handleTest() {
    setLoading(true);
    try {
      const { error } = await gateway.POST('/integrations/ha/test');
      if (error)
        Alert.alert(
          'Failed',
          errorCode(error) ?? 'Could not reach Home Assistant. Check your settings.',
        );
      else Alert.alert('Success', 'Home Assistant connection is working.');
    } catch {
      Alert.alert('Error', 'Network error.');
    } finally {
      setLoading(false);
    }
  }

  async function handleDisconnect() {
    setLoading(true);
    try {
      const { error } = await gateway.POST('/integrations/ha/disconnect');
      if (error) {
        Alert.alert('Error', errorCode(error) ?? 'Failed to disconnect.');
        return;
      }
      await refreshStatus();
      setBaseUrl('');
      setToken('');
      onDisconnected?.();
      Alert.alert('Disconnected', 'Home Assistant has been disconnected.');
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
          {t('integrations.ha.family_note')}
        </Text>

        {connected ? (
          <Text style={[typography.caption, { color: colors.fg2 }]}>
            {t('integrations.ha.connected_by', {
              name: status.connected_by ?? '—',
              date: status.connected_at
                ? new Date(status.connected_at).toLocaleDateString(appLocale())
                : '—',
            })}
          </Text>
        ) : (
          <>
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
              editable={!loading}
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
              editable={!loading}
            />
          </>
        )}
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
