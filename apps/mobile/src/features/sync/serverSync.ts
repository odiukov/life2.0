import { apiBaseUrl } from '@/api/client';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';

/** Fire-and-forget: kicks off Garmin + Yazio sync on the server. */
export async function triggerServerSync(): Promise<void> {
  try {
    const headers = await getAuthHeaders();
    await fetch(`${apiBaseUrl}/sync/trigger`, {
      method: 'POST',
      headers,
    });
  } catch (e) {
    console.warn('[sync] server sync trigger failed:', e);
  }
}
