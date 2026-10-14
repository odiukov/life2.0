import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Screen, useTheme } from '@life-agents/ui';
import { useRouter } from 'expo-router';
import { supabase, SUPABASE_CONFIGURED } from './SupabaseClient';

export function EmailMagicLinkScreen() {
  const { colors, spacing, typography } = useTheme();
  const router = useRouter();
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSend() {
    if (!email.trim()) return;
    setLoading(true);
    setError(null);
    try {
      if (SUPABASE_CONFIGURED) {
        const { error: sbError } = await supabase.auth.signInWithOtp({
          email: email.trim(),
          options: { emailRedirectTo: 'lifeagents://auth-callback' },
        });
        if (sbError) {
          setError(sbError.message);
          return;
        }
      }
      setSent(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Screen edges={['top', 'bottom']}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Back to sign in"
        hitSlop={12}
        style={[styles.back, { marginTop: spacing.s4, marginLeft: spacing.s4 }]}
        onPress={() => router.replace('/(auth)/sign-in')}
      >
        <Text style={[typography.body, { color: colors.fg2 }]}>← Back to sign in</Text>
      </Pressable>
      <View style={[styles.container, { padding: spacing.s4 }]}>
        {sent ? (
          <>
            <Text style={[typography.display, { color: colors.fg1, marginBottom: spacing.s2 }]}>
              Check your inbox
            </Text>
            <Text style={[typography.body, { color: colors.fg2 }]}>
              We sent a magic link to {email}. Tap it to sign in.
            </Text>
          </>
        ) : (
          <>
            <Text style={[typography.display, { color: colors.fg1, marginBottom: spacing.s2 }]}>
              Email sign-in
            </Text>
            <Text style={[typography.body, { color: colors.fg2, marginBottom: spacing.s4 }]}>
              We&apos;ll send you a magic link to sign in instantly.
            </Text>

            <TextInput
              testID="email-input"
              style={[
                styles.input,
                {
                  backgroundColor: colors.bg3,
                  color: colors.fg1,
                  padding: spacing.s3,
                  marginBottom: spacing.s2,
                  borderRadius: 12,
                },
              ]}
              placeholder="you@example.com"
              placeholderTextColor={colors.fg2}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoCorrect={false}
            />

            {error && (
              <Text
                style={[typography.caption, { color: colors.danger, marginBottom: spacing.s2 }]}
              >
                {error}
              </Text>
            )}

            <Pressable
              testID="send-magic-link"
              style={[styles.button, { backgroundColor: colors.fg1, padding: spacing.s3 }]}
              onPress={handleSend}
              disabled={loading}
            >
              <Text style={[typography.body, { color: colors.bg1, textAlign: 'center' }]}>
                {loading ? 'Sending…' : 'Send me a link'}
              </Text>
            </Pressable>
          </>
        )}
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  back: {
    alignSelf: 'flex-start',
  },
  button: {
    borderRadius: 12,
  },
  container: {
    flex: 1,
    justifyContent: 'center',
  },
  input: {
    fontSize: 16,
  },
});
