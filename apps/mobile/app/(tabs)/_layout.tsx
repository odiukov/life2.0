import { Tabs } from 'expo-router';
import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Icon, useTheme } from '@life-agents/ui';
import { DevBanner } from '@/api/DevBanner';

export default function TabsLayout() {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  return (
    <View style={{ flex: 1 }}>
      <Tabs
        sceneContainerStyle={{ backgroundColor: colors.bg0 }}
        screenOptions={{
          headerShown: false,
          tabBarStyle: { backgroundColor: colors.bg1, borderTopColor: colors.border },
          tabBarActiveTintColor: colors.accentHi,
          tabBarInactiveTintColor: colors.fg3,
        }}
      >
        {/* Visible tabs */}
        <Tabs.Screen
          name="index"
          options={{ title: 'Home', tabBarIcon: ({ color }) => <Icon name="House" size={22} color={color} /> }}
        />
        <Tabs.Screen
          name="chat"
          options={{ title: 'Chat', tabBarIcon: ({ color }) => <Icon name="ChatCircle" size={22} color={color} /> }}
        />
      </Tabs>
      <View style={{ position: 'absolute', top: insets.top, left: 0, right: 0 }}>
        <DevBanner />
      </View>
    </View>
  );
}
