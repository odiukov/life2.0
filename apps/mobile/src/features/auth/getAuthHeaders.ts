import { DEV_USER_ID, validAccessToken } from './useSession';

export { DEV_USER_ID };

export async function getAuthHeaders(): Promise<Record<string, string>> {
  if (DEV_USER_ID) return { 'X-User-Id': DEV_USER_ID };
  const token = await validAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
