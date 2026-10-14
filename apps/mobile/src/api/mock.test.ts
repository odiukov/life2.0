import { mockFetch } from './mock';

let fetchMock: ReturnType<typeof mockFetch>;

beforeEach(() => {
  fetchMock = mockFetch();
});

async function call(method: string, path: string, body?: unknown) {
  const response = await fetchMock(`http://mock.local${path}`, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return {
    status: response.status,
    json: response.status === 204 ? null : await response.json(),
  };
}

describe('gateway mock routes', () => {
  it.each([
    ['GET', '/household'],
    ['PATCH', '/household'],
    ['POST', '/household/invites'],
    ['POST', '/household/join/preview'],
    ['POST', '/household/join'],
    ['POST', '/household/leave'],
    ['GET', '/kitchen/inventory'],
    ['GET', '/kitchen/digest'],
    ['GET', '/notifications'],
    ['POST', '/notifications/read-all'],
    ['POST', '/voice/transcribe'],
  ])('%s %s is implemented', async (method, path) => {
    const body = path.startsWith('/household/join') ? { code: 'DEMO-2026' } : undefined;
    expect((await call(method, path, body)).status).toBe(200);
  });

  it('accepts every no-content route', async () => {
    expect((await call('DELETE', '/household/members/member')).status).toBe(204);
    expect(
      (await call('POST', '/notifications/55555555-5555-5555-5555-555555555555/read')).status,
    ).toBe(204);
    expect(
      (await call('POST', '/me/push-tokens', { token: 'ExponentPushToken[x]', platform: 'ios' }))
        .status,
    ).toBe(204);
    expect((await call('DELETE', '/me/push-tokens/ExponentPushToken%5Bx%5D')).status).toBe(204);
  });

  it('updates inventory on action and restores it on undo', async () => {
    const inventory = (await call('GET', '/kitchen/inventory')).json;
    const id = inventory.items[0].id;
    const acted = await call('POST', `/kitchen/items/${id}/action`, { action: 'consumed' });
    expect(acted.status).toBe(200);
    expect(
      (await call('GET', '/kitchen/inventory')).json.items.some(
        (item: { id: string }) => item.id === id,
      ),
    ).toBe(false);
    expect((await call('POST', `/kitchen/undo/${acted.json.group_id}`)).json).toEqual({
      outcome: 'done',
    });
    expect(
      (await call('GET', '/kitchen/inventory')).json.items.some(
        (item: { id: string }) => item.id === id,
      ),
    ).toBe(true);
  });

  it('updates unread count when a notification is read', async () => {
    const inbox = (await call('GET', '/notifications')).json;
    expect(inbox.items.length).toBeGreaterThan(0);
    expect(inbox.unread_count).toBe(1);
    const id = inbox.items[0].id;
    expect((await call('POST', `/notifications/${id}/read`)).status).toBe(204);
    const updated = (await call('GET', '/notifications')).json;
    expect(updated.items.find((item: { id: string }) => item.id === id).read_at).not.toBeNull();
    expect(updated.unread_count).toBe(0);
  });

  it('keeps household changes consistent across routes', async () => {
    const original = (await call('GET', '/household')).json;
    expect(
      (await call('POST', '/household/join/preview', { code: 'DEMO-2026' })).json.items_to_move,
    ).toBe(3);
    const joined = (await call('POST', '/household/join', { code: 'DEMO-2026' })).json;
    expect(joined.id).not.toBe(original.id);
    expect(joined.members).toHaveLength(2);
    expect((await call('GET', '/household')).json.id).toBe(joined.id);
    expect((await call('POST', '/household/leave')).json.id).toBe(original.id);
  });

  it('rejects an invalid invite and marks all notifications read', async () => {
    expect((await call('POST', '/household/join/preview', { code: 'invalid' })).status).toBe(404);
    expect((await call('POST', '/notifications/read-all')).json.updated).toBe(1);
    expect((await call('GET', '/notifications')).json.unread_count).toBe(0);
  });

  it('uses the household calendar day across Lisbon midnight', async () => {
    fetchMock = mockFetch(new Date('2026-07-14T23:30:00Z'));
    const inventory = (await call('GET', '/kitchen/inventory')).json;
    const digest = (await call('GET', '/kitchen/digest')).json;
    expect(
      inventory.items.find((item: { name: string }) => item.name === 'Chicken').expires_on,
    ).toBe('2026-07-15');
    expect(digest.today.map((item: { name: string }) => item.name)).toEqual(['Chicken']);
    expect(digest.tomorrow.map((item: { name: string }) => item.name)).toEqual(['Milk']);
  });

  it('returns an English sample transcript', async () => {
    expect((await call('POST', '/voice/transcribe')).json).toEqual({ text: 'Bought bread' });
  });
});
