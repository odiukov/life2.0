import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { BottomTabBarProps } from '@react-navigation/bottom-tabs';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon, useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { TaskButton } from './TaskButton';

const TABS = [
  { name: 'index', icon: 'User', label: 'tabs.me' },
  { name: 'house', icon: 'House', label: 'tabs.house' },
] as const;

export function TaskTabBar({ state, navigation }: BottomTabBarProps) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const t = useT(appLocale());
  const current = state.routes[state.index]?.name;

  const tab = (spec: (typeof TABS)[number]) => {
    const route = state.routes.find((r) => r.name === spec.name);
    const focused = current === spec.name;
    const color = focused ? colors.accentHi : colors.fg3;
    return (
      <Pressable
        key={spec.name}
        testID={`tab-${spec.name}`}
        accessibilityRole="tab"
        accessibilityState={{ selected: focused }}
        onPress={() => {
          if (!route) return;
          const event = navigation.emit({
            type: 'tabPress',
            target: route.key,
            canPreventDefault: true,
          });
          if (!focused && !event.defaultPrevented) navigation.navigate(spec.name);
        }}
        style={styles.tab}
      >
        <Icon name={spec.icon} size={22} color={color} />
        <Text style={{ color, fontSize: 10.5, marginTop: 2 }}>{t(spec.label)}</Text>
      </Pressable>
    );
  };

  return (
    <View
      style={[
        styles.bar,
        {
          paddingBottom: insets.bottom,
          backgroundColor: colors.bg1,
          borderTopColor: colors.border,
        },
      ]}
    >
      {tab(TABS[0])}
      <TaskButton />
      {tab(TABS[1])}
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    alignItems: 'flex-start',
    borderTopWidth: StyleSheet.hairlineWidth,
    flexDirection: 'row',
    justifyContent: 'space-around',
    paddingTop: 10,
  },
  tab: { alignItems: 'center', width: 88 },
});
