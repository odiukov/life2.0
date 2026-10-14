import { useEffect } from 'react';
import 'react-native-url-polyfill/auto';
import { useRouter } from 'expo-router';
import * as Linking from 'expo-linking';
import { useSession } from './useSession';

/** Handles the deep link when the browser hands control to a cold app. */
export default function AuthCallbackScreen() {
  const router = useRouter();
  useEffect(() => {
    async function apply(url: string | null | undefined) {
      if (!url) return;
      try {
        const parsed = new URL(url.replace('lifeagents://', 'https://placeholder/'));
        const ticket = parsed.searchParams.get('ticket');
        if (!ticket) return;
        await useSession.getState().completeSignIn(ticket);
        router.replace('/(tabs)/chat');
      } catch {
        // Never log callback data, which can include a one-time ticket.
        console.warn('[auth-callback] exchange_failed'); // eslint-disable-line no-console
      }
    }
    void Linking.getInitialURL()
      .then(apply)
      .catch(() => {});
    const sub = Linking.addEventListener('url', (event) => {
      void apply(event.url);
    });
    return () => sub.remove();
  }, [router]);
  return null;
}
