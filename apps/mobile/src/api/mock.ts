import type { paths } from '@life-agents/api-client';

type Fetch = typeof fetch;

const routes: Record<string, () => unknown> = {
  'GET /chat/threads': () => [
    { id: 't1', title: 'Today', updated_at: new Date().toISOString() },
  ],
  'GET /dashboard': () => ({
    agents: [
      { agent: 'sleep',      label: 'Sleep',      metric: '7h12m',     tint: 'success' },
      { agent: 'recovery',   label: 'Recovery',   metric: 'Recovered', tint: 'success' },
      { agent: 'workout',    label: 'Workout',    metric: 'Z2 60m',    tint: 'neutral' },
      { agent: 'nutrition',  label: 'Nutrition',  metric: '1840 kcal', tint: 'neutral' },
      { agent: 'mood',       label: 'Mood',       metric: '7/10',      tint: 'success' },
      { agent: 'habits',     label: 'Habits',     metric: '2/3',       tint: 'warn' },
      { agent: 'medication', label: 'Medication', metric: 'B12 −2d',   tint: 'warn' },
      { agent: 'finance',    label: 'Finance',    metric: '$4,231',    tint: 'success' },
    ],
  }),
  'GET /today': () => ({
    greeting: 'Good morning',
    date: new Date().toISOString().slice(0, 10),
    status_pills: [
      { tone: 'success', label: 'Recovered' },
      { tone: 'warn',    label: 'Missed med' },
    ],
    must_see: ['Slept 7h12m · 94%', '3 meetings · first free 14:00'],
    alerts: [
      {
        id: 'a1',
        title: 'Missed B12 for 2d',
        body: 'Active medication logged zero times in past 48h.',
        category: 'wellness',
        severity: 'warn',
        created_at: new Date(Date.now() - 3600_000).toISOString(),
      },
    ],
  }),
  'GET /me': () => ({ id: 'me', voice_preset: 'calm_coach' }),
};

export function mockFetch(): Fetch {
  return async (input, init) => {
    const url = typeof input === 'string' ? input : (input as URL).toString();
    const method = init?.method?.toUpperCase() ?? 'GET';
    const pathname = new URL(url, 'http://mock.local').pathname;
    const key = `${method} ${pathname}`;
    const handler = routes[key];
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
