import React from 'react';
import { Alert, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { Card, Screen, useTheme } from '@life-agents/ui';
import { useSession } from '@/features/auth/useSession';
import { SUPABASE_CONFIGURED } from '@/features/auth/SupabaseClient';

const NAV_ROWS = [
  { to: '/(tabs)/more/integrations', label: 'Integrations', hint: 'Connected sources', icon: '⚡' },
  { to: '/(tabs)/more/tone', label: 'Agent tone of voice', hint: 'Calm coach', icon: '💬' },
  { to: '/(tabs)/more/privacy', label: 'Privacy & data', hint: 'On-device by default', icon: '⚙' },
  { to: '/(tabs)/more/subscription', label: 'Subscription', hint: 'Life+ · monthly', icon: '⚙' },
  { to: '/(tabs)/more/about', label: 'About Life Agents', hint: 'v0.0.1', icon: '⚙' },
] as const;

export function MoreScreen() {
  const router = useRouter();
  const { colors, spacing, typography } = useTheme();
  const signOut = useSession((s) => s.signOut);
  const session = useSession((s) => s.session);

  const email = session?.user?.email ?? null;
  const displayName = session?.user?.user_metadata?.full_name as string | undefined;
  const initials = (displayName ?? email ?? 'U')
    .split(' ')
    .map((w: string) => w[0] ?? '')
    .join('')
    .toUpperCase()
    .slice(0, 2);

  function confirmSignOut() {
    Alert.alert('Sign out?', 'You can sign back in at any time.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Sign out',
        style: 'destructive',
        onPress: async () => {
          await signOut();
        },
      },
    ]);
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: spacing.s4, gap: spacing.s4 }}>
        {/* Profile card */}
        <Card>
          <View style={styles.profileRow}>
            <View style={[styles.avatar, { backgroundColor: colors.accent }]}>
              <Text style={{ color: colors.accentInk, fontWeight: '700', fontSize: 18 }}>
                {initials}
              </Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[typography.bodyEm, { color: colors.fg1 }]}>
                {displayName ?? 'Life User'}
              </Text>
              {email && <Text style={[typography.caption, { color: colors.fg3 }]}>{email}</Text>}
            </View>
            <View style={[styles.lifePlusBadge, { backgroundColor: colors.accent }]}>
              <Text
                style={{
                  color: colors.accentInk,
                  fontSize: 10,
                  fontWeight: '700',
                  letterSpacing: 0.5,
                }}
              >
                LIFE+
              </Text>
            </View>
          </View>
        </Card>

        {/* Settings list */}
        <View>
          <Text style={[typography.micro, { color: colors.fg3, marginBottom: spacing.s2 }]}>
            SETTINGS
          </Text>
          <Card pad={0}>
            {NAV_ROWS.map((row, i) => (
              <Pressable
                key={row.to}
                onPress={() => router.push(row.to as never)}
                style={[
                  styles.navRow,
                  i > 0 && { borderTopWidth: 1, borderTopColor: colors.borderSoft },
                ]}
              >
                <View style={[styles.iconChip, { backgroundColor: colors.bg3 }]}>
                  <Text style={{ fontSize: 15 }}>{row.icon}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[typography.body, { color: colors.fg1, fontWeight: '600' }]}>
                    {row.label}
                  </Text>
                  <Text style={[typography.caption, { color: colors.fg3, marginTop: 1 }]}>
                    {row.hint}
                  </Text>
                </View>
                <Text style={{ color: colors.fg4, fontSize: 16 }}>›</Text>
              </Pressable>
            ))}
          </Card>
        </View>

        {SUPABASE_CONFIGURED && session && (
          <Pressable
            testID="sign-out"
            onPress={confirmSignOut}
            style={[styles.signOut, { backgroundColor: colors.danger }]}
          >
            <Text style={[typography.bodyEm, { color: '#fff', textAlign: 'center' }]}>
              Sign out
            </Text>
          </Pressable>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  profileRow: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
  },
  lifePlusBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  navRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
  iconChip: {
    width: 30,
    height: 30,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  signOut: { borderRadius: 12, padding: 14 },
});
