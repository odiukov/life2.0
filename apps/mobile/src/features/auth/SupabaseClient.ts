import 'react-native-url-polyfill/auto';
import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import * as SecureStore from 'expo-secure-store';

const SB_URL = process.env.EXPO_PUBLIC_SUPABASE_URL ?? '';
const SB_ANON = process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY ?? '';

export const SUPABASE_CONFIGURED = Boolean(SB_URL && SB_ANON);

const SecureStoreAdapter = {
  getItem: (k: string) => SecureStore.getItemAsync(k),
  setItem: (k: string, v: string) => SecureStore.setItemAsync(k, v),
  removeItem: (k: string) => SecureStore.deleteItemAsync(k),
};

/**
 * Supabase client. When env vars are absent (dev mode before the Supabase
 * project exists) the real client isn't constructed — supabase-js throws on
 * empty URL. Instead we expose a stub whose auth methods resolve to a
 * not-configured error / empty session, keeping the app bootable and letting
 * the sign-in screen surface the "not configured" banner.
 */
function makeStubClient(): SupabaseClient {
  const notConfigured = () =>
    Promise.resolve({
      data: { session: null, user: null, url: null },
      error: { message: 'Supabase not configured', name: 'NotConfigured', status: 0 } as any,
    });
  const authStub = {
    getSession: notConfigured,
    signInWithOAuth: notConfigured,
    signInWithOtp: notConfigured,
    signInWithPassword: notConfigured,
    signOut: () => Promise.resolve({ error: null }),
    exchangeCodeForSession: notConfigured,
    setSession: notConfigured,
    onAuthStateChange: (_cb: (...a: unknown[]) => void) => ({
      data: { subscription: { unsubscribe: () => {} } },
    }),
  };
  return { auth: authStub } as unknown as SupabaseClient;
}

export const supabase: SupabaseClient = SUPABASE_CONFIGURED
  ? createClient(SB_URL, SB_ANON, {
      auth: {
        storage: SecureStoreAdapter,
        autoRefreshToken: true,
        persistSession: true,
        detectSessionInUrl: false,
        // PKCE flow is the recommended path for native apps. Supabase appends
        // a `code` query param to the redirect URL; the client holds a
        // code_verifier in SecureStore between signInWithOtp() and
        // exchangeCodeForSession(code). Without this, Supabase falls back to
        // implicit flow with tokens in the URL hash fragment.
        flowType: 'pkce',
      },
    })
  : makeStubClient();
