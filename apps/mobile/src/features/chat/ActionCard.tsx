import React, { useEffect, useRef, useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { Card, useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import type { ActionState } from './taskEvents';

type Props = {
  action: ActionState;
  onConfirm(): void | Promise<void>;
  onReject(): void | Promise<void>;
  now?: () => number;
};

const mmss = (ms: number) => {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

export function ActionCard({ action, onConfirm, onReject, now = Date.now }: Props) {
  const t = useT(appLocale());
  const { colors, spacing, typography, radius } = useTheme();
  const [tapped, setTapped] = useState(false);
  const tapping = useRef(false);
  const [clock, setClock] = useState(now());
  useEffect(() => {
    if (action.status !== 'pending') return;
    const id = setInterval(() => setClock(now()), 1000);
    return () => clearInterval(id);
  }, [action.status, now]);

  const left = action.expiresAt ? Date.parse(action.expiresAt) - clock : null;
  const status =
    action.status === 'pending' && left !== null && left <= 0 ? 'expired' : action.status;
  const tap = (fn: () => void | Promise<void>) => () => {
    if (tapping.current) return;
    tapping.current = true;
    setTapped(true);
    const result = fn();
    if (result)
      void result
        .finally(() => {
          tapping.current = false;
          setTapped(false);
        })
        .catch(() => undefined);
  };
  const button = (
    testID: string,
    label: string,
    onPress: () => void | Promise<void>,
    primary: boolean,
  ) => (
    <Pressable
      testID={testID}
      accessibilityRole="button"
      disabled={tapped}
      onPress={tap(onPress)}
      style={{
        flex: 1,
        padding: spacing.s2,
        borderRadius: radius.rMd,
        alignItems: 'center',
        backgroundColor: primary ? colors.accent : colors.bg2,
        opacity: tapped ? 0.5 : 1,
      }}
    >
      <Text style={[typography.bodyEm, { color: primary ? colors.accentInk : colors.fg1 }]}>
        {label}
      </Text>
    </Pressable>
  );

  return (
    <Card>
      <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{action.summary}</Text>
      {status === 'pending' ? (
        <>
          {left !== null && (
            <Text style={[typography.caption, { color: colors.fg3, marginTop: spacing.s1 }]}>
              {t('chat.action.expires_in', { time: mmss(left) })}
            </Text>
          )}
          <View style={{ flexDirection: 'row', gap: spacing.s2, marginTop: spacing.s2 }}>
            {button('action-reject', t('chat.action.reject'), onReject, false)}
            {button('action-confirm', t('chat.action.confirm'), onConfirm, true)}
          </View>
        </>
      ) : (
        <Text
          style={[
            typography.caption,
            { color: status === 'failed' ? colors.danger : colors.fg2, marginTop: spacing.s1 },
          ]}
        >
          {action.message || t(`chat.action.status.${status}`)}
        </Text>
      )}
    </Card>
  );
}
