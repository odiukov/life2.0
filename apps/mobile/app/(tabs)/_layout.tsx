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
        screenOptions={{
          headerShown: false,
          tabBarStyle: { backgroundColor: colors.bg1, borderTopColor: colors.border },
          tabBarActiveTintColor: colors.accentHi,
          tabBarInactiveTintColor: colors.fg3,
        }}
      >
        <Tabs.Screen name="chat" options={{ title: 'Chat', tabBarIcon: ({ color }) => <Icon name="ChatCircle" size={22} color={color} /> }} />
        <Tabs.Screen name="today" options={{ title: 'Today', tabBarIcon: ({ color }) => <Icon name="Sun" size={22} color={color} /> }} />
        <Tabs.Screen name="dash" options={{ title: 'Dash', tabBarIcon: ({ color }) => <Icon name="SquaresFour" size={22} color={color} /> }} />
        <Tabs.Screen name="more" options={{ title: 'More', tabBarIcon: ({ color }) => <Icon name="DotsThree" size={22} color={color} /> }} />
      </Tabs>
      {/* DevBanner floats inside the safe-area gap that Screen's SafeAreaView already creates.
          Absolutely positioned here (inside Stack) so the Tabs navigator sees a clean
          full-screen coordinate space and its initial tab-bar height calculation is correct. */}
      <View style={{ position: 'absolute', top: insets.top, left: 0, right: 0 }}>
        <DevBanner />
      </View>
    </View>
  );
}
