import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { Screen, useTheme } from '@life-agents/ui';
import { supabase, SUPABASE_CONFIGURED } from './SupabaseClient';

export function EmailMagicLinkScreen() {
  const { colors, spacing, typography } = useTheme();
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

  if (sent) {
    return (
      <Screen edges={['top', 'bottom']}>
        <View style={[styles.container, { padding: spacing.s4 }]}>
          <Text style={[typography.display, { color: colors.fg1, marginBottom: spacing.s2 }]}>
            Check your inbox
          </Text>
          <Text style={[typography.body, { color: colors.fg2 }]}>
            We sent a magic link to {email}. Tap it to sign in.
          </Text>
        </View>
      </Screen>
    );
  }

  return (
    <Screen edges={['top', 'bottom']}>
      <View style={[styles.container, { padding: spacing.s4 }]}>
        <Text style={[typography.display, { color: colors.fg1, marginBottom: spacing.s2 }]}>
          Email sign-in
        </Text>
        <Text style={[typography.body, { color: colors.fg2, marginBottom: spacing.s4 }]}>
          We'll send you a magic link to sign in instantly.
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
          <Text style={[typography.caption, { color: colors.danger, marginBottom: spacing.s2 }]}>
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
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
  },
  input: {
    fontSize: 16,
  },
  button: {
    borderRadius: 12,
  },
});
