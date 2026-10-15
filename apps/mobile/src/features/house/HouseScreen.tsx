import React, { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { useHousehold } from '../household/useHousehold';
import { IntegrationSheet } from '../integrations/IntegrationSheet';
import { KitchenScreen } from '../kitchen/KitchenScreen';
import { useHaStatus } from '../integrations/useHaStatus';
import { SettingsSheet } from '../more/SettingsSheet';

export function HouseScreen() {
  const t = useT(appLocale());
  const { colors, spacing, radius } = useTheme();
  const household = useHousehold();
  const ha = useHaStatus();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [haOpen, setHaOpen] = useState(false);
  const members = household.data?.members ?? [];

  const row = {
    flexDirection: 'row' as const,
    alignItems: 'center' as const,
    gap: spacing.s2,
    padding: spacing.s3,
    borderRadius: radius.rMd,
    backgroundColor: colors.bg2,
    borderWidth: 1,
    borderColor: colors.borderSoft,
  };
  const header = (
    <View style={{ paddingHorizontal: spacing.s4, paddingTop: spacing.s3, gap: spacing.s2 }}>
      <Pressable
        testID="house-household"
        accessibilityRole="button"
        onPress={() => setSettingsOpen(true)}
        style={row}
      >
        <Text
          style={{ flex: 1, color: colors.fg1, fontSize: 16, fontWeight: '600' }}
          numberOfLines={1}
        >
          {household.data?.name ?? t('house.title')}
        </Text>
        <View style={{ flexDirection: 'row' }}>
          {members.slice(0, 5).map((m, i) => (
            <View
              key={m.user_id}
              style={{
                width: 26,
                height: 26,
                borderRadius: 13,
                marginLeft: i ? -6 : 0,
                backgroundColor: colors.bg4,
                borderWidth: 2,
                borderColor: colors.bg2,
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Text style={{ color: colors.fg1, fontSize: 11, fontWeight: '700' }}>
                {(m.name || '?').slice(0, 1).toUpperCase()}
              </Text>
            </View>
          ))}
        </View>
        <Text style={{ color: colors.accentHi, fontSize: 13 }}>{t('house.invite')}</Text>
      </Pressable>
      <Pressable
        testID="house-smart-home"
        accessibilityRole="button"
        onPress={() => setHaOpen(true)}
        style={row}
      >
        <Text style={{ color: colors.fg1, fontSize: 14 }}>🏠 {t('house.smart_home.title')}</Text>
        <Text
          style={{ flex: 1, textAlign: 'right', color: colors.fg3, fontSize: 12.5 }}
          numberOfLines={1}
        >
          {ha.data?.connected
            ? t('house.smart_home.connected', { name: ha.data.connected_by ?? '' })
            : t('house.smart_home.connect')}
        </Text>
      </Pressable>
    </View>
  );

  return (
    <>
      <KitchenScreen header={header} />
      <SettingsSheet
        visible={settingsOpen}
        initialPanel="household"
        onClose={() => setSettingsOpen(false)}
      />
      <IntegrationSheet
        integration={haOpen ? 'ha' : null}
        onClose={() => {
          setHaOpen(false);
          void ha.refetch();
        }}
      />
    </>
  );
}
