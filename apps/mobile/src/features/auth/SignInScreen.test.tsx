import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { openAuthSessionAsync } from 'expo-web-browser';
import { SignInScreen } from './SignInScreen';

const mockSignInWithOAuth = jest.fn();
const mockExchangeCodeForSession = jest.fn();

jest.mock('./SupabaseClient', () => ({
  SUPABASE_CONFIGURED: true,
  supabase: {
    auth: {
      signInWithOAuth: (...args: unknown[]) => mockSignInWithOAuth(...args),
      exchangeCodeForSession: (...args: unknown[]) => mockExchangeCodeForSession(...args),
    },
  },
}));

test('does not log an OAuth callback code', async () => {
  const log = jest.spyOn(console, 'log').mockImplementation(() => {});
  const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
  mockSignInWithOAuth.mockResolvedValue({
    data: { url: 'https://example.invalid/auth' },
    error: null,
  });
  jest.mocked(openAuthSessionAsync).mockResolvedValue({
    type: 'success',
    url: 'lifeagents://auth-callback?code=private-marker',
  });
  mockExchangeCodeForSession.mockResolvedValue({ error: null });

  try {
    render(
      <ThemeProvider>
        <SignInScreen />
      </ThemeProvider>,
    );
    fireEvent.press(screen.getByTestId('sign-in-apple'));
    await waitFor(() => expect(mockExchangeCodeForSession).toHaveBeenCalledWith('private-marker'));

    const output = [...log.mock.calls, ...warn.mock.calls].flat().join(' ');
    expect(output).not.toContain('private-marker');
  } finally {
    log.mockRestore();
    warn.mockRestore();
  }
});

test('does not expose OAuth failure details', async () => {
  const warn = jest.spyOn(console, 'warn').mockImplementation(() => {});
  mockSignInWithOAuth.mockRejectedValue(new Error('private-marker'));

  try {
    render(
      <ThemeProvider>
        <SignInScreen />
      </ThemeProvider>,
    );
    fireEvent.press(screen.getByTestId('sign-in-apple'));

    await waitFor(() => expect(warn).toHaveBeenCalledWith('[signInWithOAuth] unavailable'));
    expect(warn.mock.calls.flat().join(' ')).not.toContain('private-marker');
  } finally {
    warn.mockRestore();
  }
});
