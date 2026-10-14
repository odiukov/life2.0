import { createGatewayClient } from '@life-agents/api-client';
import type { Middleware } from 'openapi-fetch';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';
import { apiBaseUrl, apiMode } from './client';
import { mockFetch } from './mock';

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const headers = await getAuthHeaders();
    for (const [name, value] of Object.entries(headers)) request.headers.set(name, value);
    return request;
  },
};

export const gateway = createGatewayClient({
  baseUrl: apiBaseUrl,
  fetch: apiMode === 'mock' ? mockFetch() : undefined,
});
gateway.use(authMiddleware);

/** Error code from a gateway error body ({"detail": "item_gone"}), or null. */
export function errorCode(error: unknown): string | null {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return typeof detail === 'string' ? detail : null;
}
