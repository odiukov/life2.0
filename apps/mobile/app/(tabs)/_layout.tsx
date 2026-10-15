import { Tabs } from 'expo-router';
import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { DevBanner } from '@/api/DevBanner';
import { appLocale } from '@/lib/locale';
import { TaskSheet } from '@/features/task/TaskSheet';
import { TaskTabBar } from '@/features/task/TaskTabBar';

export default function TabsLayout() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const t = useT(appLocale());
  return (
    <View style={{ flex: 1 }}>
      <Tabs
        tabBar={(props) => <TaskTabBar {...props} />}
        screenOptions={{ sceneStyle: { backgroundColor: colors.bg0 }, headerShown: false }}
      >
        <Tabs.Screen name="index" options={{ title: t('tabs.me') }} />
        <Tabs.Screen name="house" options={{ title: t('tabs.house') }} />
      </Tabs>
      <TaskSheet />
      <View
        style={{ position: 'absolute', top: insets.top, left: 0, right: 0 }}
        pointerEvents="box-none"
      >
        <DevBanner />
      </View>
    </View>
  );
}
