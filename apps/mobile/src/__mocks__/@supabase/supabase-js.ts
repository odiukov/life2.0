// Jest mock for @supabase/supabase-js
export type Session = {
  access_token: string;
  refresh_token: string;
  user: { id: string; email?: string };
};

const noopAuth = {
  getSession: jest.fn(async () => ({ data: { session: null }, error: null })),
  onAuthStateChange: jest.fn(() => ({ data: { subscription: { unsubscribe: jest.fn() } } })),
  signOut: jest.fn(async () => ({ error: null })),
  signInWithOAuth: jest.fn(async () => ({ data: { url: null, provider: null }, error: null })),
  signInWithOtp: jest.fn(async () => ({ data: {}, error: null })),
  setSession: jest.fn(async () => ({ data: { session: null }, error: null })),
  exchangeCodeForSession: jest.fn(async () => ({ data: { session: null }, error: null })),
};

export const createClient = jest.fn(() => ({
  auth: noopAuth,
}));
