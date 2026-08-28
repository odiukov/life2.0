import React from 'react';
import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';
import { Screen, useTheme } from '@life-agents/ui';
import { useRouter } from 'expo-router';
import { supabase, SUPABASE_CONFIGURED } from './SupabaseClient';

let openAuthSessionAsync: ((url: string, redirectUrl?: string) => Promise<{ type: string; url?: string } | void>) | undefined;
try {
  // eslint-disable-next-line @typescript-eslint/no-var-requires
  const WebBrowser = require('expo-web-browser') as typeof import('expo-web-browser');
  openAuthSessionAsync = WebBrowser.openAuthSessionAsync;
} catch {
  openAuthSessionAsync = (url: string) => Linking.openURL(url).then(() => undefined);
}

const REDIRECT_URL = 'lifeagents://auth-callback';

async function signInWithOAuth(provider: 'apple' | 'google') {
  if (!SUPABASE_CONFIGURED) return;
  const { data, error } = await supabase.auth.signInWithOAuth({
    provider,
    options: { redirectTo: REDIRECT_URL, skipBrowserRedirect: true },
  });
  if (error || !data.url) {
    // eslint-disable-next-line no-console
    console.warn('[signInWithOAuth] start failed', error);
    return;
  }
  if (!openAuthSessionAsync) {
    await Linking.openURL(data.url);
    return;
  }
  // openAuthSessionAsync intercepts the redirect back to REDIRECT_URL and
  // resolves with { type: 'success', url: '<redirect>?code=...&state=...' }.
  // With flowType: 'pkce' we must exchange the code ourselves — the in-app
  // AuthCallbackScreen never fires because the browser tab is a modal, not a
  // system deep link.
  const result = await openAuthSessionAsync(data.url, REDIRECT_URL);
  if (!result || result.type !== 'success' || !result.url) {
    // eslint-disable-next-line no-console
    console.log('[signInWithOAuth] cancelled or closed', result);
    return;
  }
  // eslint-disable-next-line no-console
  console.log('[signInWithOAuth] callback URL', result.url);
  const url = new URL(result.url.replace('lifeagents://', 'https://placeholder/'));
  const code = url.searchParams.get('code');
  if (code) {
    const { error: exchangeErr } = await supabase.auth.exchangeCodeForSession(code);
    if (exchangeErr) {
      // eslint-disable-next-line no-console
      console.warn('[signInWithOAuth] exchange failed', exchangeErr);
    }
    return;
  }
  // Implicit-flow fallback: tokens in the hash fragment
  const hash = result.url.split('#')[1] ?? '';
  const params = new URLSearchParams(hash);
  const access = params.get('access_token');
  const refresh = params.get('refresh_token');
  if (access && refresh) {
    await supabase.auth.setSession({ access_token: access, refresh_token: refresh });
  }
}

export function SignInScreen() {
  const { colors, spacing, typography } = useTheme();
  const router = useRouter();

  return (
    <Screen edges={['top', 'bottom']}>
      <View style={[styles.container, { padding: spacing.s4 }]}>
        {!SUPABASE_CONFIGURED && (
          <View style={[styles.banner, { backgroundColor: colors.warn, padding: spacing.s2, marginBottom: spacing.s3 }]}>
            <Text style={[typography.caption, { color: '#000' }]}>
              Supabase not configured — set EXPO_PUBLIC_SUPABASE_URL in .env.local
            </Text>
          </View>
        )}

        <Text style={[typography.display, { color: colors.fg1, marginBottom: spacing.s2 }]}>
          Sign in
        </Text>
        <Text style={[typography.body, { color: colors.fg2, marginBottom: spacing.s5 }]}>
          Your personal AI health system
        </Text>

        <Pressable
          testID="sign-in-apple"
          style={[styles.button, { backgroundColor: colors.fg1, padding: spacing.s3, marginBottom: spacing.s2 }]}
          onPress={() => signInWithOAuth('apple')}
        >
          <Text style={[typography.body, { color: colors.bg1, textAlign: 'center' }]}>
            Sign in with Apple
          </Text>
        </Pressable>

        <Pressable
          testID="sign-in-google"
          style={[styles.button, { backgroundColor: colors.bg3, padding: spacing.s3, marginBottom: spacing.s2 }]}
          onPress={() => signInWithOAuth('google')}
        >
          <Text style={[typography.body, { color: colors.fg1, textAlign: 'center' }]}>
            Sign in with Google
          </Text>
        </Pressable>

        <Pressable
          testID="sign-in-email"
          style={[styles.button, { padding: spacing.s3 }]}
          onPress={() => router.push('/(auth)/email')}
        >
          <Text style={[typography.body, { color: colors.fg2, textAlign: 'center' }]}>
            Sign in with email
          </Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
  },
  button: {
    borderRadius: 12,
  },
  banner: {
    borderRadius: 8,
  },
});
