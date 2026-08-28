import type { paths } from '@life-agents/api-client';

type Fetch = typeof fetch;

const routes: Record<string, () => unknown> = {
  'GET /chat/threads': () => [{ id: 't1', title: 'Today', updated_at: new Date().toISOString() }],
  'GET /dashboard': () => ({
    agents: [
      { agent: 'sleep', label: 'Sleep', metric: '7h12m', tint: 'success' },
      { agent: 'recovery', label: 'Recovery', metric: 'Recovered', tint: 'success' },
      { agent: 'workout', label: 'Workout', metric: 'Z2 60m', tint: 'neutral' },
      { agent: 'nutrition', label: 'Nutrition', metric: '1840 kcal', tint: 'neutral' },
      { agent: 'mood', label: 'Mood', metric: '7/10', tint: 'success' },
      { agent: 'habits', label: 'Habits', metric: '2/3', tint: 'warn' },
      { agent: 'medication', label: 'Medication', metric: 'B12 −2d', tint: 'warn' },
      { agent: 'finance', label: 'Finance', metric: '$4,231', tint: 'success' },
    ],
  }),
  'GET /dashboard/summary': () => ({
    agents: [
      { agent: 'sleep', label: 'Sleep', metric: '7h12m', tint: 'success' },
      { agent: 'recovery', label: 'Recovery', metric: 'Recovered', tint: 'success' },
      { agent: 'workout', label: 'Workout', metric: 'Z2 60m', tint: 'neutral' },
      { agent: 'nutrition', label: 'Nutrition', metric: '1840 kcal', tint: 'neutral' },
      { agent: 'mood', label: 'Mood', metric: '7/10', tint: 'success' },
      { agent: 'habits', label: 'Habits', metric: '2/3', tint: 'warn' },
      { agent: 'medication', label: 'Medication', metric: 'B12 −2d', tint: 'warn' },
      { agent: 'finance', label: 'Finance', metric: '$4,231', tint: 'success' },
    ],
  }),
  'GET /me': () => ({ id: 'me', voice_preset: 'calm_coach' }),
};

export function mockFetch(): Fetch {
  return async (input, init) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof Request
          ? input.url
          : (input as URL).toString();
    const method =
      (input instanceof Request ? input.method : null) ?? init?.method?.toUpperCase() ?? 'GET';
    const pathname = new URL(url, 'http://mock.local').pathname;
    const key = `${method} ${pathname}`;
    const handler = routes[key];

    // Dynamic route: GET /agents/{agent_id}/detail
    if (!handler && method === 'GET') {
      const detailMatch = pathname.match(/^\/agents\/([^/]+)\/detail$/);
      if (detailMatch) {
        const agentId = detailMatch[1];
        await new Promise((r) => setTimeout(r, 120));
        return new Response(
          JSON.stringify({
            agent: agentId,
            insight: `Mock insight for ${agentId}. Looking good.`,
            metrics: { mock_value: 42, mock_label: 'Sample' },
            history: Array.from({ length: 7 }, (_, i) => ({
              date: new Date(Date.now() - (6 - i) * 86400000).toISOString().split('T')[0],
              value: 5 + i * 0.5,
              label: `${(5 + i * 0.5).toFixed(1)}`,
            })),
          }),
          { status: 200, headers: { 'content-type': 'application/json' } },
        );
      }
    }

    if (!handler) {
      return new Response('not mocked: ' + key, { status: 501 });
    }
    await new Promise((r) => setTimeout(r, 120));
    return new Response(JSON.stringify(handler()), {
      status: 200,
      headers: { 'content-type': 'application/json' },
    });
  };
}

export type _paths = paths;
