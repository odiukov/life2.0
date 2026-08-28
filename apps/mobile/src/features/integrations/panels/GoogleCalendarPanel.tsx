import React, { useEffect, useState } from 'react';
import { Alert, Pressable, ScrollView, Text } from 'react-native';
import * as SecureStore from 'expo-secure-store';
import * as WebBrowser from 'expo-web-browser';
import { Card, useTheme } from '@life-agents/ui';
import { apiBaseUrl } from '@/api/client';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';

const GCAL_KEY = 'gcal_connected';
const REDIRECT_URI = 'com.googleusercontent.apps.90325200012-h74926clm7els3i32qjns4vskfurvln1:/integrations-callback';

type Props = {
  onConnected?: () => void;
  onDisconnected?: () => void;
  onScroll?: React.ComponentProps<typeof ScrollView>['onScroll'];
  scrollEventThrottle?: number;
};

export function GoogleCalendarPanel({
  onConnected,
  onDisconnected,
  onScroll,
  scrollEventThrottle,
}: Props) {
  const { colors, spacing, typography, radius } = useTheme();
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    SecureStore.getItemAsync(GCAL_KEY).then((v) => { if (v) setConnected(true); });
  }, []);

  async function handleConnect() {
    setLoading(true);
    try {
      const headers = await getAuthHeaders();

      const startRes = await fetch(`${apiBaseUrl}/integrations/google_calendar/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
      });
      if (!startRes.ok) {
        const body = await startRes.json().catch(() => ({}));
        Alert.alert('Error', body?.detail ?? 'Failed to start Google Calendar auth.');
        return;
      }
      const { auth_url, state } = (await startRes.json()) as { auth_url: string; state: string };

      const result = await WebBrowser.openAuthSessionAsync(auth_url, REDIRECT_URI);
      if (result.type !== 'success' || !result.url) return;

      const url = new URL(result.url);
      const code = url.searchParams.get('code');
      const returnedState = url.searchParams.get('state');
      if (!code || !returnedState) {
        Alert.alert('Error', 'Missing code or state from Google callback.');
        return;
      }

      const callbackRes = await fetch(`${apiBaseUrl}/integrations/google_calendar/callback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
        body: JSON.stringify({ code, state: returnedState }),
      });
      if (callbackRes.ok) {
        await SecureStore.setItemAsync(GCAL_KEY, '1');
        setConnected(true);
        onConnected?.();
        Alert.alert('Connected', 'Google Calendar connected successfully.');
      } else {
        const body = await callbackRes.json().catch(() => ({}));
        Alert.alert('Error', body?.detail ?? 'Failed to complete Google Calendar auth.');
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
      const res = await fetch(`${apiBaseUrl}/integrations/google_calendar/disconnect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...headers },
      });
      if (res.ok) {
        await SecureStore.deleteItemAsync(GCAL_KEY);
        setConnected(false);
        onDisconnected?.();
        Alert.alert('Disconnected', 'Google Calendar has been disconnected.');
      } else {
        Alert.alert('Error', 'Failed to disconnect.');
      }
    } catch {
      Alert.alert('Error', 'Network error.');
    } finally {
      setLoading(false);
    }
  }

  const btnStyle = (variant: 'primary' | 'danger') => ({
    backgroundColor: variant === 'primary' ? colors.accent : colors.danger,
    borderRadius: radius.rMd,
    padding: spacing.s3,
    alignItems: 'center' as const,
    opacity: loading ? 0.6 : 1,
  });

  return (
    <ScrollView
      testID="google-calendar-scroll"
      onScroll={onScroll}
      scrollEventThrottle={scrollEventThrottle}
      contentContainerStyle={{ padding: spacing.s3, gap: spacing.s3 }}
    >
      <Card>
        <Text style={[typography.bodyEm, { color: colors.fg1, marginBottom: spacing.s2 }]}>
          Google Calendar
        </Text>
        <Text style={[typography.caption, { color: colors.fg2 }]}>
          {connected
            ? 'Your Google Calendar is connected. Events will be synced automatically.'
            : 'Connect your Google Calendar to let your agent see your schedule and upcoming events.'}
        </Text>
      </Card>

      {!connected ? (
        <Pressable testID="google-calendar-connect" onPress={handleConnect} disabled={loading} style={btnStyle('primary')}>
          <Text style={[typography.bodyEm, { color: '#fff' }]}>
            {loading ? 'Connecting…' : 'Connect Calendar'}
          </Text>
        </Pressable>
      ) : (
        <Pressable testID="google-calendar-disconnect" onPress={handleDisconnect} disabled={loading} style={btnStyle('danger')}>
          <Text style={[typography.bodyEm, { color: '#fff' }]}>Disconnect</Text>
        </Pressable>
      )}
    </ScrollView>
  );
}
