import React, { useEffect, useState } from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { Card, ScreenState, useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { errorCode } from '@/api/gateway';
import { appLocale } from '@/lib/locale';
import { formatInviteInput } from './inviteCode';
import { useHousehold, useHouseholdMutations } from './useHousehold';

const KNOWN_ERRORS = new Set([
  'invite_invalid',
  'invite_own',
  'invite_rate_limited',
  'not_owner',
  'household_sole_member',
]);

const styles = StyleSheet.create({
  codeText: { letterSpacing: 2 },
  input: { borderRadius: 10, borderWidth: 1, flex: 1, padding: 10 },
  joinRow: { flexDirection: 'row' },
  memberRow: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between' },
  scrollContent: { paddingBottom: 32 },
});

export function HouseholdPanel() {
  const { colors, spacing, typography } = useTheme();
  const t = useT(appLocale());
  const { data, isLoading, isError, refetch } = useHousehold();
  const mutations = useHouseholdMutations();
  const [code, setCode] = useState('');
  const [invite, setInvite] = useState<{ householdId: string; code: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    setCode('');
    setInvite(null);
    setMessage(null);
  }, [data?.id]);

  const explain = (error: unknown) => {
    const code = errorCode(error);
    setMessage(t(`household.errors.${code && KNOWN_ERRORS.has(code) ? code : 'generic'}`));
  };

  if (isLoading) return <ScreenState kind="loading" />;
  if (isError || !data) {
    return (
      <ScreenState
        kind="error"
        title={t('household.errors.generic')}
        cta={{ label: t('states.retry'), onPress: () => void refetch() }}
      />
    );
  }

  const isOwner = data.my_role === 'owner';
  const activeInvite = invite?.householdId === data.id ? invite.code : null;

  const startJoin = async () => {
    setMessage(null);
    try {
      const preview = await mutations.preview.mutateAsync(code);
      const moves =
        preview.items_to_move > 0
          ? `\n${t('household.join_moves', { count: preview.items_to_move })}`
          : '';
      Alert.alert(
        t('household.join'),
        t('household.join_preview', {
          name: preview.household_name,
          members: preview.member_count,
        }) + moves,
        [
          { text: t('household.cancel'), style: 'cancel' },
          {
            text: t('household.join'),
            onPress: () => {
              void mutations.join
                .mutateAsync(code)
                .then(() => setCode(''))
                .catch(explain);
            },
          },
        ],
      );
    } catch (error) {
      explain(error);
    }
  };

  return (
    <ScrollView
      contentContainerStyle={[styles.scrollContent, { padding: spacing.s4, gap: spacing.s3 }]}
    >
      <Text style={[typography.display, { color: colors.fg1 }]}>{data.name}</Text>
      <Text style={[typography.caption, { color: colors.fg3 }]}>{t('household.members')}</Text>
      {data.members.map((member) => (
        <Card key={member.user_id}>
          <View style={styles.memberRow}>
            <Text style={[typography.bodyEm, { color: colors.fg1 }]}>
              {member.role === 'owner' ? `${member.name} · ${t('household.owner')}` : member.name}
            </Text>
            {isOwner && member.role !== 'owner' && (
              <Pressable
                onPress={() =>
                  Alert.alert(
                    t('household.remove'),
                    t('household.remove_confirm', { name: member.name }),
                    [
                      { text: t('household.cancel'), style: 'cancel' },
                      {
                        text: t('household.remove'),
                        style: 'destructive',
                        onPress: () =>
                          mutations.remove.mutate(member.user_id, { onError: explain }),
                      },
                    ],
                  )
                }
              >
                <Text style={{ color: colors.danger }}>{t('household.remove')}</Text>
              </Pressable>
            )}
          </View>
        </Card>
      ))}

      <Pressable
        onPress={() =>
          void mutations.invite
            .mutateAsync()
            .then((result) => setInvite({ householdId: data.id, code: result.code }))
            .catch(explain)
        }
      >
        <Card>
          <Text style={[typography.bodyEm, { color: colors.accentHi }]}>
            {t('household.invite')}
          </Text>
        </Card>
      </Pressable>
      {activeInvite && (
        <Card>
          <Text selectable style={[typography.display, styles.codeText, { color: colors.fg1 }]}>
            {activeInvite}
          </Text>
          <Text style={[typography.caption, { color: colors.fg3 }]}>
            {t('household.invite_hint')}
          </Text>
          <Pressable
            onPress={() =>
              void Share.share({
                message: t('household.share_message', { code: activeInvite }),
              }).catch(explain)
            }
          >
            <Text style={{ color: colors.accentHi, marginTop: spacing.s2 }}>
              {t('household.share')}
            </Text>
          </Pressable>
        </Card>
      )}

      <Text style={[typography.caption, { color: colors.fg3 }]}>{t('household.enter_code')}</Text>
      <View style={[styles.joinRow, { gap: spacing.s2 }]}>
        <TextInput
          value={code}
          onChangeText={(raw) => setCode(formatInviteInput(raw))}
          placeholder="XXXX-XXXX"
          autoCapitalize="characters"
          autoCorrect={false}
          style={[styles.input, { color: colors.fg1, borderColor: colors.border }]}
        />
        <Pressable onPress={() => void startJoin()} disabled={code.length < 9}>
          <Card>
            <Text style={{ color: colors.accentHi }}>{t('household.join')}</Text>
          </Card>
        </Pressable>
      </View>
      {message && <Text style={{ color: colors.danger }}>{message}</Text>}

      <Pressable
        onPress={() =>
          Alert.alert(t('household.leave'), t('household.leave_confirm'), [
            { text: t('household.cancel'), style: 'cancel' },
            {
              text: t('household.leave'),
              style: 'destructive',
              onPress: () => void mutations.leave.mutateAsync().catch(explain),
            },
          ])
        }
      >
        <Text style={{ color: colors.danger, marginTop: spacing.s4 }}>{t('household.leave')}</Text>
      </Pressable>
    </ScrollView>
  );
}
