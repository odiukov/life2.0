import { createApiClient } from '@life-agents/api-client';
import { mockFetch } from './mock';

const USE_MOCK = true; // flipped false when P2 backend endpoints land

export const api = createApiClient({
  baseUrl: 'http://mock.local',
  fetch: USE_MOCK ? mockFetch() : undefined,
});
