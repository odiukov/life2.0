import React from 'react';
import { Pressable, Text, View, StyleSheet } from 'react-native';
import { Icon, useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { AgentStack } from './AgentStack';
export function MeHeader({
  now,
  unreadBadge,
  onInbox,
  onSettings,
  agentsOnline,
  onAgents,
}: {
  now: Date;
  unreadBadge: string | null;
  onInbox: () => void;
  onSettings: () => void;
  agentsOnline: number | null;
  onAgents: () => void;
}) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  const dateLabel = now.toLocaleDateString(appLocale(), {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  });
  return (
    <View style={styles.header}>
      <View style={{ flex: 1, minWidth: 0, marginRight: 12 }}>
        <Text
          style={{
            fontSize: 11,
            color: colors.fg3,
            fontWeight: '600',
            letterSpacing: 0.5,
            textTransform: 'uppercase',
          }}
        >
          {dateLabel}
        </Text>
      </View>
      <AgentStack online={agentsOnline} onPress={onAgents} />
      <Pressable
        testID="inbox-bell"
        accessibilityRole="button"
        accessibilityLabel={t('inbox.title')}
        onPress={() => onInbox()}
        style={[
          styles.settingsBtn,
          { backgroundColor: colors.bg2, borderColor: colors.border, marginRight: 8 },
        ]}
      >
        <Icon name="Bell" size={17} color={colors.fg2} />
        {unreadBadge && (
          <View
            style={{
              position: 'absolute',
              top: -4,
              right: -4,
              minWidth: 16,
              height: 16,
              borderRadius: 8,
              backgroundColor: colors.danger,
              alignItems: 'center',
              justifyContent: 'center',
              paddingHorizontal: 3,
            }}
          >
            <Text style={{ color: colors.accentInk, fontSize: 10, fontWeight: '700' }}>
              {unreadBadge}
            </Text>
          </View>
        )}
      </Pressable>
      <Pressable
        accessibilityRole="button"
        testID="me-settings"
        accessibilityLabel={t('voice.open_settings')}
        onPress={() => onSettings()}
        style={[styles.settingsBtn, { backgroundColor: colors.bg2, borderColor: colors.border }]}
      >
        <Icon name="Gear" size={17} color={colors.fg2} />
      </Pressable>
    </View>
  );
}
const styles = StyleSheet.create({
  header: { alignItems: 'center', flexDirection: 'row', paddingHorizontal: 2, paddingTop: 8 },
  settingsBtn: {
    alignItems: 'center',
    borderRadius: 19,
    borderWidth: 1,
    height: 38,
    justifyContent: 'center',
    width: 38,
  },
});
