import { useCallback, useEffect, useState } from 'react';
import { Stack, useRouter, useSegments, router } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { KeyboardProvider } from 'react-native-keyboard-controller';
import { ThemeProvider } from '@life-agents/ui';
import { StatusBar } from 'expo-status-bar';
import * as Linking from 'expo-linking';
import * as Notifications from 'expo-notifications';
import { QueryProvider } from '@/api/QueryProvider';
import { useSession } from '@/features/auth/useSession';
import { shareAttachment } from '@/features/task/share';
import { openTask } from '@/features/task/sheetStore';
import { useHydrateIntegrations } from '@/features/integrations/store';
import { NOTIFICATION_ROUTES } from '@/features/inbox/InboxScreen';
import { usePushRegistration } from '@/features/inbox/registerPush';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: false,
    shouldSetBadge: false,
  }),
});

function AuthGuard({
  shareNavigationPending,
  onShareHandled,
}: {
  shareNavigationPending: boolean;
  onShareHandled: () => void;
}) {
  const { session, ready } = useSession();
  const segments = useSegments();
  const router = useRouter();

  useHydrateIntegrations(Boolean(session));

  useEffect(() => {
    // `segments` is empty on first render (before the Root Layout has mounted
    // the Stack). Imperative navigation then throws "Attempted to navigate
    // before mounting". Wait for segments to populate before redirecting.
    // (TS types segments as `1 | 2 | 3 | 4`-length tuples; cast to guard.)
    if (!ready || (segments as string[]).length === 0) return;
    const inAuthGroup = segments[0] === '(auth)';
    if (!session && !inAuthGroup) {
      router.replace('/(auth)/sign-in');
    } else if (session && inAuthGroup) {
      router.replace('/(tabs)');
    }
  }, [session, ready, segments, router]);

  // The root Stack and authentication must settle before a share changes routes.
  // The attachment itself was already queued, including when sign-in is needed.
  useEffect(() => {
    if (!shareNavigationPending || !ready || !session || (segments as string[]).length === 0)
      return;
    if (segments[0] !== '(auth)' && segments[0] !== '(tabs)') router.push('/(tabs)');
    // The existing auth redirect handles the auth group; tabs already owns the sheet.
    onShareHandled();
  }, [shareNavigationPending, ready, session, segments, router, onShareHandled]);

  useEffect(() => {
    if (session) {
      import('@/features/healthkit/background')
        .then((m) => m.registerBackgroundSync())
        .catch(() => {});
      import('@/features/healthkit/sync').then((m) => m.runSync()).catch(() => {});
      import('@/features/sync/serverSync').then((m) => m.triggerServerSync()).catch(() => {});
    }
  }, [session]);

  return null;
}

export default function RootLayout() {
  const { ready } = useSession();
  usePushRegistration();
  const [shareNavigationPending, setShareNavigationPending] = useState(false);
  const onShareHandled = useCallback(() => setShareNavigationPending(false), []);

  // Share Extension deep link
  useEffect(() => {
    const handleShareUrl = (url: string) => {
      const attachment = shareAttachment(url);
      if (!attachment) return;
      openTask({ attachments: [attachment] });
      setShareNavigationPending(true);
    };
    const sub = Linking.addEventListener('url', ({ url }) => handleShareUrl(url));
    Linking.getInitialURL().then((url) => {
      if (url) handleShareUrl(url);
    });
    return () => sub.remove();
  }, []);

  // Notification deep-link
  useEffect(() => {
    const sub = Notifications.addNotificationResponseReceivedListener((r) => {
      const route = r.notification.request.content.data?.route;
      if (typeof route === 'string') router.push((NOTIFICATION_ROUTES[route] ?? route) as never);
    });
    // Cold-start: app launched from a notification tap
    Notifications.getLastNotificationResponseAsync().then((r) => {
      const route = r?.notification.request.content.data?.route;
      if (typeof route === 'string') router.push((NOTIFICATION_ROUTES[route] ?? route) as never);
    });
    return () => sub.remove();
  }, []);

  if (!ready) return null;

  return (
    <QueryProvider>
      <SafeAreaProvider>
        <KeyboardProvider>
          <ThemeProvider>
            <GestureHandlerRootView style={{ flex: 1, backgroundColor: '#0f0f13' }}>
              <StatusBar style="light" />
              <AuthGuard
                shareNavigationPending={shareNavigationPending}
                onShareHandled={onShareHandled}
              />
              <Stack
                screenOptions={{ headerShown: false, contentStyle: { backgroundColor: '#0f0f13' } }}
              >
                <Stack.Screen name="(tabs)" />
                <Stack.Screen name="(auth)" />
                <Stack.Screen name="inbox" />
              </Stack>
            </GestureHandlerRootView>
          </ThemeProvider>
        </KeyboardProvider>
      </SafeAreaProvider>
    </QueryProvider>
  );
}
