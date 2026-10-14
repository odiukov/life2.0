import { useEffect } from 'react';
import * as Notifications from 'expo-notifications';
import { Platform } from 'react-native';
import { apiMode } from '@/api/client';
import { gateway } from '@/api/gateway';
import { useSession } from '@/features/auth/useSession';

/** Push is optional: the in-app inbox works without an APNs entitlement. */
export async function registerForPush(expectedUserId?: string): Promise<'registered' | 'denied' | 'unavailable'> {
  if (apiMode === 'mock') return 'unavailable';
  try {
    let permission = await Notifications.getPermissionsAsync();
    if (!permission.granted && permission.canAskAgain) {
      permission = await Notifications.requestPermissionsAsync();
    }
    if (!permission.granted) return 'denied';
    const { data: token } = await Notifications.getExpoPushTokenAsync();
    if (expectedUserId && useSession.getState().session?.user.id !== expectedUserId) {
      return 'unavailable';
    }
    const { error } = await gateway.POST('/me/push-tokens', {
      body: { token, platform: Platform.OS === 'android' ? 'android' : 'ios' },
    });
    return error === undefined ? 'registered' : 'unavailable';
  } catch {
    return 'unavailable';
  }
}

/** Register on sign-in and every account switch, never for anonymous readiness. */
export function usePushRegistration(): void {
  const { ready, session } = useSession();
  const userId = ready ? session?.user.id : undefined;
  useEffect(() => {
    if (userId) void registerForPush(userId);
  }, [userId]);
}
