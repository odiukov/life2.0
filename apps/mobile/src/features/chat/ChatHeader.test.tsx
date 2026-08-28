import React from 'react';
import { fireEvent, render } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { ChatHeader } from './ChatHeader';

const mockPush = jest.fn();

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: mockPush }),
  useLocalSearchParams: () => ({}),
}));

jest.mock('@/features/agents/useAgentStatusRows', () => ({
  useAgentStatusRows: () => ({
    rows: [],
    readyCount: 3,
    totalCount: 5,
    lastSyncedAt: null,
    isSyncing: false,
    isLoading: false,
  }),
}));

jest.mock('@/lib/formatRelativeTime', () => ({
  formatRelativeTime: () => '5m ago',
}));

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

describe('ChatHeader', () => {
  beforeEach(() => mockPush.mockClear());

  it('navigates to Home tab on press', () => {
    const { getByRole } = wrap(<ChatHeader />);
    fireEvent.press(getByRole('button'));
    expect(mockPush).toHaveBeenCalledWith('/(tabs)');
  });

  it('does not render AgentStatusSheet', () => {
    const { queryByTestId } = wrap(<ChatHeader />);
    expect(queryByTestId('agent-status-sheet')).toBeNull();
  });
});
