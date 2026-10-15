import en from '@life-agents/i18n/locales/en.json';
import ru from '@life-agents/i18n/locales/ru.json';
import { appLocale } from '@/lib/locale';
type Fetch = typeof fetch;
type MockItem = {
  id: string;
  name: string;
  display_name: string;
  category: string;
  quantity: string;
  unit: string;
  location: 'fridge' | 'freezer' | 'pantry';
  opened: boolean;
  opened_on: string | null;
  expires_on: string;
  expiry_source: string;
  added_at: string;
  added_by: { user_id: string; name: string };
};

const USER_ID = '00000000-0000-0000-0000-000000000001';
const PERSONAL_ID = '99999999-9999-9999-9999-999999999999';
const JOINED_ID = '88888888-8888-8888-8888-888888888888';
const INITIAL_TIMEZONE = 'Europe/Lisbon';

function householdDate(at: Date, timezone: string, days: number): string {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat('en-US', {
      timeZone: timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
      .formatToParts(at)
      .map(({ type, value }) => [type, value]),
  ) as Record<string, string>;
  return new Date(Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day) + days))
    .toISOString()
    .slice(0, 10);
}
const mockItem = (
  id: string,
  name: string,
  days: number,
  location: MockItem['location'],
  at: Date,
): MockItem => ({
  id,
  name,
  display_name: name,
  category: 'other',
  quantity: '1',
  unit: 'pcs',
  location,
  opened: false,
  opened_on: null,
  expires_on: householdDate(at, INITIAL_TIMEZONE, days),
  expiry_source: 'estimated',
  added_at: at.toISOString(),
  added_by: { user_id: USER_ID, name: 'Demo' },
});

function json(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

function noContent(): Response {
  return new Response(null, { status: 204 });
}

export function mockFetch(today: Date = new Date()): Fetch {
  let items = [
    mockItem('11111111-1111-1111-1111-111111111111', 'Milk', 1, 'fridge', today),
    mockItem('22222222-2222-2222-2222-222222222222', 'Chicken', 0, 'fridge', today),
    mockItem('33333333-3333-3333-3333-333333333333', 'Dumplings', 60, 'freezer', today),
  ];
  let household = {
    id: PERSONAL_ID,
    name: 'Demo home',
    timezone: INITIAL_TIMEZONE,
    digest_time: '18:00',
    my_role: 'owner' as 'owner' | 'member',
    members: [{ user_id: USER_ID, name: 'Demo', role: 'owner', joined_at: today.toISOString() }],
  };
  const iso = (days: number) => householdDate(today, household.timezone, days);
  let notices = [
    {
      id: '55555555-5555-5555-5555-555555555555',
      kind: 'kitchen_digest',
      title: 'Kitchen digest',
      body: 'Check items expiring soon',
      data: { household_id: PERSONAL_ID },
      created_at: today.toISOString(),
      read_at: null as string | null,
    },
  ];
  const undo = new Map<string, { before: MockItem | null; after: MockItem | null }>();
  let sequence = 0;

  return async (input, init) => {
    const url =
      typeof input === 'string'
        ? input
        : input instanceof Request
          ? input.url
          : (input as URL).toString();
    const method = (
      init?.method ?? (input instanceof Request ? input.method : 'GET')
    ).toUpperCase();
    const parsed = new URL(url, 'http://mock.local');
    const pathname = parsed.pathname;
    const key = `${method} ${pathname}`;
    const body = init?.body ?? (input instanceof Request ? await input.clone().text() : null);
    let data: Record<string, unknown> = {};
    if (typeof body === 'string' && body) {
      try {
        data = JSON.parse(body) as Record<string, unknown>;
      } catch {
        /* Multipart and text uploads have no JSON body. */
      }
    }

    // Preserve the original app's mock endpoints.
    if (key === 'GET /me/feed') {
      const day = parsed.searchParams.get('date') ?? householdDate(today, household.timezone, 0);
      const feedText = (appLocale() === 'ru' ? ru : en).me.mock_feed;
      return json({
        date: day,
        items: [
          {
            agent: 'nutrition',
            id: 'nutrition:meal:chat:1',
            at: `${day}T12:30:00+03:00`,
            kind: 'event',
            text: feedText.meal,
          },
          {
            agent: 'sleep',
            id: 'sleep:insight',
            at: `${day}T08:00:00+03:00`,
            kind: 'insight',
            text: feedText.insight,
          },
          {
            agent: 'sleep',
            id: 'sleep:sleep_session:garmin:1',
            at: `${day}T07:40:00+03:00`,
            kind: 'event',
            text: feedText.sleep,
          },
        ],
        unavailable: [],
      });
    }

    if (key === 'GET /integrations/ha/status')
      return json({ connected: false, connected_by: null, connected_at: null });
    if (key === 'GET /dashboard' || key === 'GET /dashboard/summary')
      return json({
        unavailable: [],
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
      });
    if (key === 'GET /me') return json({ id: 'me', voice_preset: 'calm_coach' });
    const detailMatch = method === 'GET' && pathname.match(/^\/agents\/([^/]+)\/detail$/);
    if (detailMatch) {
      const agentId = detailMatch[1];
      return json({
        agent: agentId,
        insight: `Mock insight for ${agentId}. Looking good.`,
        metrics: { mock_value: 42, mock_label: 'Sample' },
        history: Array.from({ length: 7 }, (_, i) => ({
          date: new Date(Date.now() - (6 - i) * 86400000).toISOString().split('T')[0],
          value: 5 + i * 0.5,
          label: `${(5 + i * 0.5).toFixed(1)}`,
        })),
      });
    }

    if (key === 'GET /household') return json(household);
    if (key === 'PATCH /household') {
      household = {
        ...household,
        name: typeof data.name === 'string' ? data.name : household.name,
        timezone: typeof data.timezone === 'string' ? data.timezone : household.timezone,
        digest_time:
          typeof data.digest_time === 'string' ? data.digest_time : household.digest_time,
      };
      return json(household);
    }
    if (key === 'POST /household/invites')
      return json({
        code: 'DEMO-2026',
        expires_at: new Date(Date.now() + 172800000).toISOString(),
      });
    if (key === 'POST /household/join/preview') {
      if (data.code !== 'DEMO-2026') return json({ detail: 'invite_invalid' }, 404);
      return json({ household_name: 'Joined home', member_count: 1, items_to_move: items.length });
    }
    if (key === 'POST /household/join') {
      if (data.code !== 'DEMO-2026') return json({ detail: 'invite_invalid' }, 404);
      household = {
        ...household,
        id: JOINED_ID,
        name: 'Joined home',
        my_role: 'member',
        members: [
          {
            user_id: '00000000-0000-0000-0000-000000000002',
            name: 'Alex',
            role: 'owner',
            joined_at: today.toISOString(),
          },
          { user_id: USER_ID, name: 'Demo', role: 'member', joined_at: today.toISOString() },
        ],
      };
      return json(household);
    }
    if (key === 'POST /household/leave') {
      household = {
        ...household,
        id: PERSONAL_ID,
        name: 'Demo home',
        my_role: 'owner',
        members: [
          { user_id: USER_ID, name: 'Demo', role: 'owner', joined_at: today.toISOString() },
        ],
      };
      return json(household);
    }
    if (method === 'DELETE' && /^\/household\/members\/[^/]+$/.test(pathname)) {
      const memberId = pathname.split('/').at(-1);
      household = {
        ...household,
        members: household.members.filter((member) => member.user_id !== memberId),
      };
      return noContent();
    }

    if (key === 'GET /kitchen/inventory') {
      const location = parsed.searchParams.get('location');
      return json({ items: location ? items.filter((item) => item.location === location) : items });
    }
    if (key === 'GET /kitchen/digest')
      return json({
        expired: items.filter((item) => item.expires_on < iso(0)),
        today: items.filter((item) => item.expires_on === iso(0)),
        tomorrow: items.filter((item) => item.expires_on === iso(1)),
        soon: items.filter((item) => item.expires_on > iso(1) && item.expires_on <= iso(3)),
      });
    const actionMatch = method === 'POST' && pathname.match(/^\/kitchen\/items\/([^/]+)\/action$/);
    if (actionMatch) {
      const before = items.find((item) => item.id === actionMatch[1]);
      if (!before) return json({ detail: 'item_gone' }, 409);
      const groupId = `44444444-4444-4444-4444-${(++sequence).toString().padStart(12, '0')}`;
      let after: MockItem | null = null;
      if (data.action !== 'consumed' && data.action !== 'discarded') {
        after = {
          ...before,
          location:
            data.action === 'move' && typeof data.location === 'string'
              ? (data.location as MockItem['location'])
              : before.location,
          quantity:
            data.action === 'set_quantity' && data.quantity != null
              ? String(data.quantity)
              : before.quantity,
          expires_on:
            data.action === 'set_expiry' && typeof data.expires_on === 'string'
              ? data.expires_on
              : before.expires_on,
          expiry_source: data.action === 'set_expiry' ? 'corrected' : before.expiry_source,
          opened: data.action === 'opened' ? true : before.opened,
          opened_on: data.action === 'opened' ? iso(0) : before.opened_on,
        };
      }
      if (after) {
        const updated = after;
        items = items.map((item) => (item.id === before.id ? updated : item));
      } else {
        items = items.filter((item) => item.id !== before.id);
      }
      undo.set(groupId, { before, after });
      return json({ group_id: groupId, item: after });
    }
    const undoMatch = method === 'POST' && pathname.match(/^\/kitchen\/undo\/([^/]+)$/);
    if (undoMatch) {
      const groupId = undoMatch[1] ?? '';
      const change = undo.get(groupId);
      if (!change) return json({ detail: 'undo_not_found' }, 404);
      const current = items.find((item) => item.id === change.before?.id) ?? null;
      if (JSON.stringify(current) !== JSON.stringify(change.after))
        return json({ detail: 'undo_conflict' }, 409);
      items = items.filter((item) => item.id !== change.before?.id);
      if (change.before) items.push(change.before);
      undo.delete(groupId);
      return json({ outcome: 'done' });
    }

    if (key === 'GET /notifications') {
      const before = parsed.searchParams.get('before');
      const limit = Number(parsed.searchParams.get('limit') ?? 30);
      return json({
        items: notices.filter((notice) => !before || notice.created_at < before).slice(0, limit),
        unread_count: notices.filter((notice) => notice.read_at === null).length,
      });
    }
    if (key === 'POST /notifications/read-all') {
      const updated = notices.filter((notice) => notice.read_at === null).length;
      notices = notices.map((notice) => ({
        ...notice,
        read_at: notice.read_at ?? new Date().toISOString(),
      }));
      return json({ updated });
    }
    const readMatch = method === 'POST' && pathname.match(/^\/notifications\/([^/]+)\/read$/);
    if (readMatch) {
      if (!notices.some((notice) => notice.id === readMatch[1]))
        return json({ detail: 'notification_not_found' }, 404);
      notices = notices.map((notice) =>
        notice.id === readMatch[1]
          ? { ...notice, read_at: notice.read_at ?? new Date().toISOString() }
          : notice,
      );
      return noContent();
    }
    if (
      key === 'POST /me/push-tokens' ||
      (method === 'DELETE' && /^\/me\/push-tokens\/.+$/.test(pathname))
    )
      return noContent();
    if (key === 'POST /voice/transcribe') return json({ text: 'Bought bread' });
    return new Response('not mocked: ' + key, { status: 501 });
  };
}
