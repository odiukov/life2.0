import { Stack } from 'expo-router';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider } from '@life-agents/ui';
import { StatusBar } from 'expo-status-bar';
import { QueryProvider } from '@/api/QueryProvider';
import { DevBanner } from '@/api/DevBanner';

export default function RootLayout() {
  return (
    <QueryProvider>
      <SafeAreaProvider>
        <ThemeProvider>
          <StatusBar style="light" />
          <DevBanner />
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="quick-log" options={{ presentation: 'modal' }} />
          </Stack>
        </ThemeProvider>
      </SafeAreaProvider>
    </QueryProvider>
  );
}
