import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { openAuthSessionAsync } from 'expo-web-browser';
import { SignInScreen } from './SignInScreen';

const completeSignIn = jest.fn();
const beginSignIn = jest.fn().mockResolvedValue('a'.repeat(64));
jest.mock('./useSession', () => ({
  useSession: { getState: () => ({ beginSignIn, completeSignIn }) },
}));

test('Google and Apple use backend OAuth and exchange only the ticket', async () => {
  jest
    .mocked(openAuthSessionAsync)
    .mockResolvedValue({
      type: 'success',
      url: 'lifeagents://auth-callback?ticket=private-ticket',
    });
  completeSignIn.mockResolvedValue(undefined);
  render(
    <ThemeProvider>
      <SignInScreen />
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByTestId('sign-in-google'));
  await waitFor(() => expect(completeSignIn).toHaveBeenCalledWith('private-ticket'));
  expect(openAuthSessionAsync).toHaveBeenCalledWith(
    expect.stringContaining('/auth/google/start?app_challenge='),
    'lifeagents://auth-callback',
  );
  expect(screen.queryByText('Sign in with email')).toBeNull();
});
