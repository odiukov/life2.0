import { createApiClient } from '@life-agents/api-client';
import { mockFetch } from './mock';

type Mode = 'mock' | 'local' | 'cloud';

const MODE = ((process.env.EXPO_PUBLIC_API_MODE as Mode) || 'mock');

const BASE_URL =
  MODE === 'local' ? (process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000')
  : MODE === 'cloud' ? (process.env.EXPO_PUBLIC_API_BASE_URL_CLOUD || 'https://api.life-agents.app')
  : 'http://mock.local';

export const api = createApiClient({
  baseUrl: BASE_URL,
  fetch: MODE === 'mock' ? mockFetch() : undefined,
});

export const apiMode = MODE;
export const apiBaseUrl = BASE_URL;

if (__DEV__) {
  // eslint-disable-next-line no-console
  console.log('[api] mode=%s base=%s', MODE, BASE_URL);
}
