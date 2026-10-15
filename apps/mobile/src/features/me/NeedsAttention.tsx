import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { Icon, useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import type { HomeAlert } from '../home/useHomeSummary';
export function NeedsAttention({
  alerts,
  open,
  onToggle,
}: {
  alerts: HomeAlert[];
  open: boolean;
  onToggle: () => void;
}) {
  const { colors, radius, typography } = useTheme();
  const t = useT(appLocale());
  if (alerts.length === 0) return null;

  return (
    <View>
      <Pressable
        onPress={onToggle}
        style={{
          borderWidth: 1,
          borderColor: colors.borderSoft,
          borderRadius: radius.rMd,
          paddingHorizontal: 12,
          paddingVertical: 10,
          flexDirection: 'row',
          alignItems: 'center',
          gap: 10,
        }}
      >
        <View
          style={{
            width: 22,
            height: 22,
            borderRadius: 11,
            backgroundColor: colors.warnSoft,
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Icon name="Warning" size={12} color={colors.warn} />
        </View>
        <Text style={{ fontSize: 12.5, color: colors.fg1, fontWeight: '600' }}>
          {t('me.attention')}
        </Text>
        <Text
          style={{
            fontFamily: typography.mono.fontFamily,
            fontSize: 11,
            color: colors.fg3,
          }}
        >
          {alerts.length}
        </Text>
        <View style={{ flex: 1 }} />
        {!open && alerts[0] && (
          <Text numberOfLines={1} style={{ fontSize: 11.5, color: colors.fg3, maxWidth: 140 }}>
            {alerts[0].title}
          </Text>
        )}
        <Icon name={open ? 'CaretDown' : 'CaretRight'} size={14} color={colors.fg4} />
      </Pressable>
      {open && (
        <View
          style={{
            marginTop: 6,
            borderWidth: 1,
            borderColor: colors.borderSoft,
            borderRadius: radius.rMd,
            backgroundColor: colors.bg2,
            paddingHorizontal: 14,
          }}
        >
          {alerts.map((a, i) => {
            const tone =
              a.severity === 'warn'
                ? colors.warn
                : a.severity === 'info'
                  ? colors.info
                  : colors.danger;
            return (
              <View
                key={i}
                style={{
                  flexDirection: 'row',
                  gap: 12,
                  paddingVertical: 12,
                  borderTopWidth: i === 0 ? 0 : 1,
                  borderTopColor: colors.borderSoft,
                }}
              >
                <View
                  style={{
                    width: 26,
                    height: 26,
                    borderRadius: 13,
                    backgroundColor: tone + '22',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginTop: 1,
                  }}
                >
                  <Icon
                    name={a.icon === 'pill' ? 'Pill' : a.icon === 'dot' ? 'CircleIcon' : 'Warning'}
                    size={13}
                    color={tone}
                    weight={a.icon === 'dot' ? 'fill' : 'regular'}
                  />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text
                    style={{ fontSize: 13, color: colors.fg1, fontWeight: '600', marginBottom: 2 }}
                  >
                    {a.title}
                  </Text>
                  <Text style={{ fontSize: 12, color: colors.fg2, lineHeight: 17 }}>{a.body}</Text>
                </View>
              </View>
            );
          })}
        </View>
      )}
    </View>
  );
}
