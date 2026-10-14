import React from 'react';
import { renderHook, waitFor } from '@testing-library/react-native';
import * as Notifications from 'expo-notifications';
import { registerForPush, usePushRegistration } from './registerPush';

const POST = jest.fn(async (..._args: unknown[]): Promise<{ data?: undefined; error?: unknown }> => ({ data: undefined }));
jest.mock('@/api/gateway', () => ({ gateway: { POST: (...args: unknown[]) => POST(...args) } }));
jest.mock('@/api/client', () => ({ apiMode: 'local' }));
const sessionState = { ready: true, session: { user: { id: 'alice' } } as { user: { id: string } } | null };
jest.mock('@/features/auth/useSession', () => ({ useSession: Object.assign(() => sessionState, { getState: () => sessionState }) }));

beforeEach(() => {
  jest.clearAllMocks();
  (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValue({ granted: true, canAskAgain: true });
  (Notifications.getExpoPushTokenAsync as jest.Mock).mockResolvedValue({ data: 'ExponentPushToken[x]' });
  sessionState.ready = true;
  sessionState.session = { user: { id: 'alice' } };
  POST.mockResolvedValue({ data: undefined });
});

it('registers the token with the gateway', async () => {
  expect(await registerForPush()).toBe('registered');
  expect(POST).toHaveBeenCalledWith('/me/push-tokens', { body: { token: 'ExponentPushToken[x]', platform: 'ios' } });
});

it('is quiet when push is unavailable', async () => {
  (Notifications.getExpoPushTokenAsync as jest.Mock).mockRejectedValueOnce(new Error('no aps-environment'));
  expect(await registerForPush()).toBe('unavailable');
  expect(POST).not.toHaveBeenCalled();
});

it('respects a denied permission', async () => {
  (Notifications.getPermissionsAsync as jest.Mock).mockResolvedValueOnce({ granted: false, canAskAgain: false });
  expect(await registerForPush()).toBe('denied');
});

it('treats a rejected gateway response as unavailable', async () => {
  POST.mockResolvedValueOnce({ data: undefined, error: { detail: 'unavailable' } });
  expect(await registerForPush()).toBe('unavailable');
});

it('registers only for an authenticated user and retries when the account changes', async () => {
  sessionState.session = null;
  const hook = renderHook(() => usePushRegistration());
  expect(POST).not.toHaveBeenCalled();
  sessionState.session = { user: { id: 'alice' } };
  hook.rerender({});
  await waitFor(() => expect(POST).toHaveBeenCalledTimes(1));
  hook.rerender({});
  expect(POST).toHaveBeenCalledTimes(1);
  sessionState.session = { user: { id: 'bob' } };
  hook.rerender({});
  await waitFor(() => expect(POST).toHaveBeenCalledTimes(2));
  hook.unmount();
});

it('does not claim an old account token after the account changes during registration', async () => {
  let resolveToken: (value: { data: string }) => void = () => {};
  (Notifications.getExpoPushTokenAsync as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { resolveToken = resolve; }));
  const registration = registerForPush('alice');
  await waitFor(() => expect(Notifications.getExpoPushTokenAsync).toHaveBeenCalled());
  sessionState.session = { user: { id: 'bob' } };
  resolveToken({ data: 'ExponentPushToken[old]' });
  expect(await registration).toBe('unavailable');
  expect(POST).not.toHaveBeenCalled();
});
