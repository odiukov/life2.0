import React from 'react';
import 'react-native-url-polyfill/auto';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { Screen, useTheme } from '@life-agents/ui';
import { useSession } from './useSession';

let openAuthSessionAsync:
  | ((url: string, redirectUrl?: string) => Promise<{ type: string; url?: string } | void>)
  | undefined;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires, @typescript-eslint/no-require-imports
  const WebBrowser = require('expo-web-browser') as typeof import('expo-web-browser');
  openAuthSessionAsync = WebBrowser.openAuthSessionAsync;
} catch {
  openAuthSessionAsync = (url: string) => Linking.openURL(url).then(() => undefined);
}

const REDIRECT_URL = 'lifeagents://auth-callback';

async function signInWithOAuth(provider: 'apple' | 'google') {
  try {
    const mode = process.env.EXPO_PUBLIC_API_MODE || 'mock';
    const base =
      mode === 'cloud'
        ? process.env.EXPO_PUBLIC_API_BASE_URL_CLOUD || 'https://api.life-agents.app'
        : process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000';
    const challenge = await useSession.getState().beginSignIn();
    const url = `${base}/auth/${provider}/start?app_challenge=${challenge}`;
    if (!openAuthSessionAsync) {
      await Linking.openURL(url);
      return;
    }
    const result = await openAuthSessionAsync(url, REDIRECT_URL);
    if (!result || result.type !== 'success' || !result.url) {
      return;
    }
    const callback = new URL(result.url.replace('lifeagents://', 'https://placeholder/'));
    const ticket = callback.searchParams.get('ticket');
    if (ticket) await useSession.getState().completeSignIn(ticket);
  } catch {
    // eslint-disable-next-line no-console
    console.warn('[signInWithOAuth] unavailable');
  }
}

export function SignInScreen() {
  const { colors, spacing, typography } = useTheme();

  return (
    <Screen edges={['top', 'bottom']}>
      <View style={[styles.container, { padding: spacing.s4 }]}>
        <Text style={[typography.display, { color: colors.fg1, marginBottom: spacing.s2 }]}>
          Sign in
        </Text>
        <Text style={[typography.body, { color: colors.fg2, marginBottom: spacing.s5 }]}>
          Your personal AI health system
        </Text>

        <Pressable
          testID="sign-in-apple"
          style={[
            styles.button,
            { backgroundColor: colors.fg1, padding: spacing.s3, marginBottom: spacing.s2 },
          ]}
          onPress={() => signInWithOAuth('apple')}
        >
          <Text style={[typography.body, { color: colors.bg1, textAlign: 'center' }]}>
            Sign in with Apple
          </Text>
        </Pressable>

        <Pressable
          testID="sign-in-google"
          style={[
            styles.button,
            { backgroundColor: colors.bg3, padding: spacing.s3, marginBottom: spacing.s2 },
          ]}
          onPress={() => signInWithOAuth('google')}
        >
          <Text style={[typography.body, { color: colors.fg1, textAlign: 'center' }]}>
            Sign in with Google
          </Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  button: {
    borderRadius: 12,
  },
  container: {
    flex: 1,
    justifyContent: 'center',
  },
});
