import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { router } from 'expo-router';
import { EmailMagicLinkScreen } from './EmailMagicLinkScreen';

function renderEmailScreen() {
  return render(
    <ThemeProvider>
      <EmailMagicLinkScreen />
    </ThemeProvider>,
  );
}

beforeEach(() => jest.clearAllMocks());

test('returns to sign-in from the email form', () => {
  renderEmailScreen();

  fireEvent.press(screen.getByRole('button', { name: 'Back to sign in' }));

  expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in');
});

test('returns to sign-in after a magic link is requested', async () => {
  renderEmailScreen();
  fireEvent.changeText(screen.getByTestId('email-input'), 'person@example.invalid');
  fireEvent.press(screen.getByTestId('send-magic-link'));
  await screen.findByText('Check your inbox');

  fireEvent.press(screen.getByRole('button', { name: 'Back to sign in' }));

  expect(router.replace).toHaveBeenCalledWith('/(auth)/sign-in');
});
