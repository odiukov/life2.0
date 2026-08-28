import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { GoogleCalendarPanel } from './GoogleCalendarPanel';
import { HaPanel } from './HaPanel';

jest.mock('@/api/client', () => ({ apiBaseUrl: 'http://test' }));
jest.mock('@/features/auth/getAuthHeaders', () => ({
  getAuthHeaders: async () => ({}),
}));

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

test('Google Calendar panel forwards scroll events for sheet swipe coordination', () => {
  const onScroll = jest.fn();
  wrap(<GoogleCalendarPanel onScroll={onScroll} />);

  fireEvent.scroll(screen.getByTestId('google-calendar-scroll'), {
    nativeEvent: { contentOffset: { y: 80 } },
  });

  expect(onScroll).toHaveBeenCalled();
});

test('Home Assistant panel forwards scroll events for sheet swipe coordination', () => {
  const onScroll = jest.fn();
  wrap(<HaPanel onScroll={onScroll} />);

  fireEvent.scroll(screen.getByTestId('ha-scroll'), {
    nativeEvent: { contentOffset: { y: 80 } },
  });

  expect(onScroll).toHaveBeenCalled();
});
