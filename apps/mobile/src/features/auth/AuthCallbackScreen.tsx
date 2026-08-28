import { useEffect } from 'react';
import { useRouter } from 'expo-router';
import * as Linking from 'expo-linking';
import { supabase, SUPABASE_CONFIGURED } from './SupabaseClient';

/**
 * Handles the deep-link return from Supabase after a magic-link or OAuth flow.
 *
 * Supabase puts tokens in the URL **hash fragment** (`#access_token=…&refresh_token=…`),
 * not query params — Expo Router's useLocalSearchParams does NOT parse hash
 * fragments, so we read the raw URL via expo-linking and parse manually.
 *
 * Handles both cold-start (app launched by the link) via Linking.getInitialURL
 * and warm-start (app already open) via Linking.addEventListener('url').
 */
export default function AuthCallbackScreen() {
  const router = useRouter();

  useEffect(() => {
    async function apply(url: string | null | undefined) {
      if (!url) return;
      // eslint-disable-next-line no-console
      console.log('[auth-callback] incoming URL:', url);

      if (!SUPABASE_CONFIGURED) {
        router.replace('/(tabs)/chat');
        return;
      }

      const parsed = parseUrl(url);

      try {
        if (parsed.code) {
          await supabase.auth.exchangeCodeForSession(parsed.code);
        } else if (parsed.access_token && parsed.refresh_token) {
          await supabase.auth.setSession({
            access_token: parsed.access_token,
            refresh_token: parsed.refresh_token,
          });
        } else {
          // eslint-disable-next-line no-console
          console.warn('[auth-callback] no tokens in URL', parsed);
        }
      } catch (e) {
        // eslint-disable-next-line no-console
        console.warn('[auth-callback] setSession failed', e);
      }

      router.replace('/(tabs)/chat');
    }

    // Cold start — the app was launched by tapping the magic link.
    Linking.getInitialURL().then(apply);

    // Warm start — app was already running; URL arrives via event.
    const sub = Linking.addEventListener('url', (ev) => apply(ev.url));
    return () => sub.remove();
  }, [router]);

  return null;
}

/** Parse both query string (?a=1&b=2) and hash fragment (#a=1&b=2) of a URL. */
function parseUrl(url: string): Record<string, string> {
  const out: Record<string, string> = {};
  const q = url.indexOf('?');
  const h = url.indexOf('#');
  if (q >= 0) merge(out, url.slice(q + 1, h >= 0 && h > q ? h : undefined));
  if (h >= 0) merge(out, url.slice(h + 1));
  return out;
}

function merge(into: Record<string, string>, kvString: string) {
  for (const pair of kvString.split('&')) {
    if (!pair) continue;
    const eq = pair.indexOf('=');
    const k = eq >= 0 ? pair.slice(0, eq) : pair;
    const v = eq >= 0 ? pair.slice(eq + 1) : '';
    into[decodeURIComponent(k)] = decodeURIComponent(v);
  }
}
