import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';

const SESSION_KEY = 'lifeagents_auth_session';
const FLOW_VERIFIER_KEY = 'lifeagents_auth_flow_verifier';
export const DEV_USER_ID = process.env.EXPO_PUBLIC_DEV_USER_ID || '';

export type Session = {
  access_token?: string;
  refresh_token?: string;
  expires_at?: number;
  user: { id: string; email?: string | null; user_metadata?: { full_name?: string } };
};

function baseUrl(): string {
  const mode = process.env.EXPO_PUBLIC_API_MODE || 'mock';
  if (mode === 'cloud')
    return process.env.EXPO_PUBLIC_API_BASE_URL_CLOUD || 'https://api.life-agents.app';
  return process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000';
}

async function post(path: string, body: object): Promise<Session> {
  const response = await fetch(`${baseUrl()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`auth request failed: ${response.status}`);
  return response.json() as Promise<Session>;
}

async function save(session: Session | null): Promise<void> {
  if (session) await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(session));
  else await SecureStore.deleteItemAsync(SESSION_KEY);
  useSession.setState({ session });
}

export async function restoreSession(raw: string | null): Promise<Session | null> {
  if (!raw) return null;
  try {
    const session = JSON.parse(raw) as Session;
    if (!session.user?.id || !session.refresh_token) throw new Error('invalid stored session');
    if (session.access_token && (session.expires_at ?? 0) > Date.now() / 1000 + 30) return session;
    const updated = await post('/auth/refresh', { refresh_token: session.refresh_token });
    await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(updated));
    return updated;
  } catch {
    await SecureStore.deleteItemAsync(SESSION_KEY);
    return null;
  }
}

type State = {
  session: Session | null;
  ready: boolean;
  beginSignIn: () => Promise<string>;
  completeSignIn: (ticket: string) => Promise<void>;
  signOut: () => Promise<void>;
};

export const useSession = create<State>((set) => {
  if (DEV_USER_ID) {
    setTimeout(
      () =>
        set({
          session: { user: { id: DEV_USER_ID, user_metadata: { full_name: 'Demo' } } },
          ready: true,
        }),
      0,
    );
  } else {
    SecureStore.getItemAsync(SESSION_KEY)
      .then(restoreSession)
      .then((session) => set({ session, ready: true }))
      .catch(() => set({ ready: true }));
  }
  return {
    session: null,
    ready: false,
    beginSignIn: async () => {
      const verifier = Crypto.randomUUID() + Crypto.randomUUID();
      await SecureStore.setItemAsync(FLOW_VERIFIER_KEY, verifier);
      return (
        await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, verifier)
      ).toLowerCase();
    },
    completeSignIn: async (ticket) => {
      const appVerifier = await SecureStore.getItemAsync(FLOW_VERIFIER_KEY);
      if (!appVerifier) throw new Error('missing sign-in verifier');
      await save(await post('/auth/exchange', { ticket, app_verifier: appVerifier }));
      await SecureStore.deleteItemAsync(FLOW_VERIFIER_KEY);
    },
    signOut: async () => {
      const token = await validAccessToken();
      if (token) {
        try {
          await fetch(`${baseUrl()}/auth/sign-out`, {
            method: 'POST',
            headers: { Authorization: `Bearer ${token}` },
          });
        } catch {
          /* local logout still clears secrets */
        }
      }
      await save(null);
    },
  };
});

let refreshPromise: Promise<string | null> | null = null;

export async function validAccessToken(): Promise<string | null> {
  const session = useSession.getState().session;
  if (!session?.refresh_token) return session?.access_token ?? null;
  if (session.access_token && (session.expires_at ?? 0) > Date.now() / 1000 + 30)
    return session.access_token;
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const updated = await post('/auth/refresh', { refresh_token: session.refresh_token });
        await save(updated);
        return updated.access_token ?? null;
      } catch {
        await save(null);
        return null;
      } finally {
        refreshPromise = null;
      }
    })();
  }
  return refreshPromise;
}
