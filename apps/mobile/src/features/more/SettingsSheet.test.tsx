import React from 'react';
import { Text } from 'react-native';
import { ThemeProvider } from '@life-agents/ui';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { SettingsSheet } from './SettingsSheet';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('@/features/auth/useSession', () => ({
  useSession: () => ({ session: null, signOut: jest.fn() }),
}));
jest.mock('@/features/household/HouseholdPanel', () => ({
  HouseholdPanel: () => <Text>household-panel</Text>,
}));
jest.mock('@/features/integrations/panels/HaPanel', () => ({
  HaPanel: () => <Text>ha-panel</Text>,
}));
jest.mock('@/features/integrations/panels/AppleHealthPanel', () => ({ AppleHealthPanel: () => null }));
jest.mock('@/features/integrations/panels/GarminPanel', () => ({ GarminPanel: () => null }));
jest.mock('@/features/integrations/panels/GoogleCalendarPanel', () => ({
  GoogleCalendarPanel: () => null,
}));
jest.mock('@/features/integrations/panels/YazioPanel', () => ({ YazioPanel: () => null }));
jest.mock('@/features/subscription/SubscriptionScreen', () => ({
  SubscriptionContent: () => null,
}));

test('the Smart home row opens the Home Assistant panel', () => {
  render(
    <ThemeProvider>
      <SettingsSheet visible onClose={jest.fn()} />
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByText('Smart home'));
  expect(screen.getByText('ha-panel')).toBeTruthy();
});
