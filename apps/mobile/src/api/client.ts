import { createApiClient } from '@life-agents/api-client';
import type { Middleware } from 'openapi-fetch';
import { mockFetch } from './mock';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';

type Mode = 'mock' | 'local' | 'cloud';

const MODE = ((process.env.EXPO_PUBLIC_API_MODE as Mode) || 'mock');

const BASE_URL =
  MODE === 'local' ? (process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000')
  : MODE === 'cloud' ? (process.env.EXPO_PUBLIC_API_BASE_URL_CLOUD || 'https://api.life-agents.app')
  : 'http://mock.local';

const authMiddleware: Middleware = {
  async onRequest({ request }) {
    const headers = await getAuthHeaders();
    for (const [name, value] of Object.entries(headers)) request.headers.set(name, value);
    return request;
  },
};

const _client = createApiClient({
  baseUrl: BASE_URL,
  fetch: MODE === 'mock' ? mockFetch() : undefined,
});

_client.use(authMiddleware);

export const api = _client;

export const apiMode = MODE;
export const apiBaseUrl = BASE_URL;

if (__DEV__) {
  // eslint-disable-next-line no-console
  console.log('[api] mode=%s base=%s', MODE, BASE_URL);
}

export function chatStreamUrl(): string {
  return `${apiBaseUrl}/chat/stream`;
}

export function passthroughChatUrl(agent: string): string {
  return `${apiBaseUrl}/agent/${encodeURIComponent(agent)}/stream`;
}
