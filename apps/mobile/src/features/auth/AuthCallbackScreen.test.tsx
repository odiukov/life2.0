import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import * as Linking from 'expo-linking';
import AuthCallbackScreen from './AuthCallbackScreen';

const mockSetSession = jest.fn();

jest.mock('./SupabaseClient', () => ({
  SUPABASE_CONFIGURED: true,
  supabase: { auth: { setSession: (...args: unknown[]) => mockSetSession(...args) } },
}));

jest.mock('expo-linking', () => ({
  getInitialURL: jest.fn(),
  addEventListener: jest.fn(() => ({ remove: jest.fn() })),
}));

test('handles an auth callback without logging tokens', async () => {
  jest
    .mocked(Linking.getInitialURL)
    .mockResolvedValue(
      'lifeagents://auth-callback#access_token=private-access&refresh_token=private-refresh',
    );
  mockSetSession.mockResolvedValue({ error: null });
  const log = jest.spyOn(console, 'log').mockImplementation(() => {});
  const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});

  try {
    render(<AuthCallbackScreen />);
    await waitFor(() =>
      expect(mockSetSession).toHaveBeenCalledWith({
        access_token: 'private-access',
        refresh_token: 'private-refresh',
      }),
    );

    const output = [...log.mock.calls, ...warn.mock.calls].flat().join(' ');
    expect(output).not.toContain('private-access');
    expect(output).not.toContain('private-refresh');
  } finally {
    log.mockRestore();
    warn.mockRestore();
  }
});

test('does not expose a malformed callback URL', async () => {
  jest
    .mocked(Linking.getInitialURL)
    .mockResolvedValue('lifeagents://auth-callback#access_token=%private-marker');
  const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});

  try {
    render(<AuthCallbackScreen />);
    await waitFor(() => expect(warn).toHaveBeenCalledWith('[auth-callback] set_session_failed'));
    expect(warn.mock.calls.flat().join(' ')).not.toContain('private-marker');
  } finally {
    warn.mockRestore();
  }
});
