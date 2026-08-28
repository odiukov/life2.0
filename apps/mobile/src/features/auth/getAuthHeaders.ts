import { supabase, SUPABASE_CONFIGURED } from '@/features/auth/SupabaseClient';

/**
 * Local development escape hatch. With no Supabase project configured, the
 * backend can be run with `AUTH_MODE=dev`, which trusts a plain `X-User-Id`
 * header. Set `EXPO_PUBLIC_DEV_USER_ID` in `.env.local` to browse a seeded
 * demo user (see `scripts/seed_demo_data.py`). Never enable server-side in
 * production.
 */
export const DEV_USER_ID = process.env.EXPO_PUBLIC_DEV_USER_ID || '';

export async function getAuthHeaders(): Promise<Record<string, string>> {
  if (!SUPABASE_CONFIGURED) {
    return DEV_USER_ID ? { 'X-User-Id': DEV_USER_ID } : {};
  }
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}
