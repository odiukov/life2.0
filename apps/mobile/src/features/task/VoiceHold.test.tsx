import React from 'react';
import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { VoiceHold } from './VoiceHold';
jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
test('timer, cancellation hint and transcription label', () => {
  const view = (armed: boolean, transcribing: boolean) => (
    <ThemeProvider>
      <VoiceHold seconds={4} level={0.5} armed={armed} transcribing={transcribing} />
    </ThemeProvider>
  );
  const { rerender } = render(view(false, false));
  expect(screen.getByText('0:04 · release to send · ← cancel')).toBeTruthy();
  rerender(view(true, false));
  expect(screen.getByText('release to cancel')).toBeTruthy();
  rerender(view(false, true));
  expect(screen.getByText('Listening back…')).toBeTruthy();
});
