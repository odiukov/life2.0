import { Tabs } from 'expo-router';
import { Icon, useTheme } from '@life-agents/ui';

export default function TabsLayout() {
  const { colors } = useTheme();
  return (
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
  );
}
