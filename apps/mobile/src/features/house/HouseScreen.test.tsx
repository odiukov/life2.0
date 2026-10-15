import { Text } from 'react-native';
import { ThemeProvider } from '@life-agents/ui';
import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { HouseScreen } from './HouseScreen';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('../household/useHousehold', () => ({
  useHousehold: () => ({
    data: {
      id: 'h1',
      name: 'Demo home',
      timezone: 'Europe/Kyiv',
      members: [
        { user_id: 'u1', name: 'Alex' },
        { user_id: 'u2', name: 'Kate' },
      ],
    },
    refetch: jest.fn(),
  }),
}));
jest.mock('../kitchen/KitchenScreen', () => ({
  KitchenScreen: ({ header }: { header: React.ReactNode }) => header,
}));
jest.mock('../more/SettingsSheet', () => ({
  SettingsSheet: ({ visible, initialPanel }: { visible: boolean; initialPanel?: string }) =>
    visible ? <Text>{`settings:${initialPanel}`}</Text> : null,
}));
jest.mock('../integrations/IntegrationSheet', () => ({
  IntegrationSheet: ({ integration }: { integration: string | null }) =>
    integration ? <Text>{`integration:${integration}`}</Text> : null,
}));

test('the household strip opens the household panel; the smart-home row opens HA', () => {
  render(
    <ThemeProvider>
      <HouseScreen />
    </ThemeProvider>,
  );
  expect(screen.getByText('Demo home')).toBeTruthy();
  fireEvent.press(screen.getByTestId('house-household'));
  expect(screen.getByText('settings:household')).toBeTruthy();
  fireEvent.press(screen.getByTestId('house-smart-home'));
  expect(screen.getByText('integration:ha')).toBeTruthy();
});

jest.mock('../integrations/useHaStatus', () => ({
  useHaStatus: () => ({ data: { connected: false }, refetch: jest.fn() }),
}));
