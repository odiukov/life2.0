import { getAuthHeaders } from './getAuthHeaders';
import * as SecureStore from 'expo-secure-store';
import { restoreSession, useSession } from './useSession';

test('restoring an expired session refreshes before exposing the user', async () => {
  const previous = {
    access_token: 'expired-access',
    refresh_token: 'current-refresh',
    expires_at: 1,
    user: { id: 'user-id' },
  };
  const updated = {
    access_token: 'fresh-access',
    refresh_token: 'rotated-refresh',
    expires_at: Math.floor(Date.now() / 1000) + 900,
    user: { id: 'user-id' },
  };
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => updated });

  expect(await restoreSession(JSON.stringify(previous))).toEqual(updated);
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/auth/refresh'),
    expect.objectContaining({ body: JSON.stringify({ refresh_token: 'current-refresh' }) }),
  );
  expect(SecureStore.setItemAsync).toHaveBeenCalledWith(
    'lifeagents_auth_session',
    JSON.stringify(updated),
  );
});

test('restoring a revoked session clears it before the app becomes ready', async () => {
  const previous = {
    access_token: 'expired-access',
    refresh_token: 'revoked-refresh',
    expires_at: 1,
    user: { id: 'user-id' },
  };
  global.fetch = jest.fn().mockResolvedValue({ ok: false, status: 401 });

  expect(await restoreSession(JSON.stringify(previous))).toBeNull();
  expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('lifeagents_auth_session');
});

test('exchanges a one-time ticket and sends our access token', async () => {
  const response = {
    access_token: 'app-access',
    refresh_token: 'app-refresh',
    expires_at: Math.floor(Date.now() / 1000) + 900,
    user: { id: 'user-id', email: null, user_metadata: { full_name: 'Test' } },
  };
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => response });
  expect(await useSession.getState().beginSignIn()).toBe('a'.repeat(64));
  await useSession.getState().completeSignIn('one-use-ticket');
  expect(global.fetch).toHaveBeenCalledWith(
    expect.stringContaining('/auth/exchange'),
    expect.objectContaining({ body: expect.stringContaining('app_verifier') }),
  );
  expect(await getAuthHeaders()).toEqual({ Authorization: 'Bearer app-access' });
  expect(useSession.getState().session?.user.id).toBe('user-id');
});

test('sign out refreshes an expired access token before revoking the server session', async () => {
  useSession.setState({
    session: {
      access_token: 'expired-access',
      refresh_token: 'current-refresh',
      expires_at: 1,
      user: { id: 'user-id' },
    },
  });
  const response = {
    access_token: 'fresh-access',
    refresh_token: 'rotated-refresh',
    expires_at: Math.floor(Date.now() / 1000) + 900,
    user: { id: 'user-id' },
  };
  global.fetch = jest
    .fn()
    .mockResolvedValueOnce({ ok: true, json: async () => response })
    .mockResolvedValueOnce({ ok: true });
  await useSession.getState().signOut();
  expect(global.fetch).toHaveBeenNthCalledWith(
    2,
    expect.stringContaining('/auth/sign-out'),
    expect.objectContaining({ headers: { Authorization: 'Bearer fresh-access' } }),
  );
  expect(useSession.getState().session).toBeNull();
});
