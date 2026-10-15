import React from 'react';
import { Text, Pressable, ScrollView } from 'react-native';
import { ThemeProvider } from '@life-agents/ui';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { MeScreen } from './MeScreen';
import { feedDay } from './useDayFeed';
import type { AgentRow } from '../agents/agentStatusRules';
import { openTask } from '../task/sheetStore';

const mockSummaryRefetch = jest.fn();
const mockFeedRefetch = jest.fn();
const mockRefresh = jest.fn();
const mockPush = jest.fn();
const mockRouter = { push: mockPush };
let mockFocus: (() => void) | undefined;
let mockSummaryError = false;
let mockFeedError = false;
let mockNutrition = false;
let mockRows: AgentRow[] = [];
jest.mock('../task/sheetStore', () => ({ openTask: jest.fn() }));
const mockUseDayFeed = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => mockRouter,
  useFocusEffect: (callback: () => void) => {
    mockFocus = callback;
  },
}));
jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('../home/useHomeSummary', () => ({
  useHomeSummary: () => ({
    data: mockSummaryError
      ? undefined
      : {
          agents: mockNutrition
            ? [{ agent: 'nutrition', metric: '640 kcal', progress: null }]
            : [{ agent: 'sleep', metric: '7h 40m', progress: 0.9 }],
          unavailable: [],
        },
    isError: mockSummaryError,
    refetch: mockSummaryRefetch,
    onRefresh: mockRefresh,
    isRefreshing: false,
  }),
}));
jest.mock('./useDayFeed', () => ({
  ...jest.requireActual('./useDayFeed'),
  useDayFeed: (day: string) => {
    mockUseDayFeed(day);
    return {
      data: mockFeedError
        ? undefined
        : {
            date: day,
            items: [
              {
                agent: 'sleep',
                id: 's1',
                at: `${day}T08:00:00Z`,
                kind: 'event',
                text: 'Slept well',
              },
            ],
            unavailable: [],
          },
      isLoading: false,
      isError: mockFeedError,
      isRefetching: false,
      refetch: mockFeedRefetch,
    };
  },
}));
jest.mock('../auth/useSession', () => ({
  useSession: () => ({ session: { user: { user_metadata: { full_name: 'Alex Smith' } } } }),
}));
jest.mock('../inbox/useInbox', () => ({ useInbox: () => ({ data: { unread_count: 3 } }) }));
jest.mock('../agents/useAgentStatusRows', () => ({
  useAgentStatusRows: () => ({ rows: mockRows }),
}));
jest.mock('../more/SettingsSheet', () => ({
  SettingsSheet: ({ visible }: { visible: boolean }) => (visible ? <Text>settings</Text> : null),
}));
jest.mock('../home/AgentDetailSheet', () => ({
  AgentDetailSheet: ({ visible, agentId }: { visible: boolean; agentId: string }) =>
    visible ? <Text>{`detail:${agentId}`}</Text> : null,
}));
jest.mock('../integrations/IntegrationSheet', () => ({
  IntegrationSheet: ({ integration }: { integration: string | null }) =>
    integration ? <Text>{`integration:${integration}`}</Text> : null,
}));
jest.mock('../home/BodyProfileSheet', () => ({
  BodyProfileSheet: ({ visible, onSaved }: { visible: boolean; onSaved: () => void }) =>
    visible ? (
      <Pressable onPress={onSaved}>
        <Text>profile sheet</Text>
      </Pressable>
    ) : null,
}));

beforeEach(() => {
  jest.clearAllMocks();
  mockSummaryError = false;
  mockFeedError = false;
  mockNutrition = false;
  mockRows = [];
});
function mount() {
  return render(
    <ThemeProvider>
      <MeScreen />
    </ThemeProvider>,
  );
}

test('greets by first name, opens feed agents, changes day and refreshes both queries', () => {
  const result = mount();
  expect(screen.getByText(/Alex$/)).toBeTruthy();
  fireEvent.press(screen.getByText('Slept well'));
  expect(screen.getByText('detail:sleep')).toBeTruthy();
  fireEvent.press(screen.getByLabelText('Previous day'));
  expect(mockUseDayFeed).toHaveBeenLastCalledWith(feedDay(new Date(), 1));
  const refresh = result.UNSAFE_getAllByType(ScrollView).find((view) => view.props.refreshControl)
    ?.props.refreshControl;
  act(() => refresh.props.onRefresh());
  expect(mockRefresh).toHaveBeenCalledTimes(1);
  expect(mockFeedRefetch).toHaveBeenCalledTimes(1);
});

test('refreshes summary and selected day on each navigation focus', () => {
  mount();
  act(() => mockFocus?.());
  act(() => mockFocus?.());
  expect(mockSummaryRefetch).toHaveBeenCalledTimes(2);
  expect(mockFeedRefetch).toHaveBeenCalledTimes(2);
  fireEvent.press(screen.getByLabelText('Previous day'));
  act(() => mockFocus?.());
  expect(mockFeedRefetch).toHaveBeenCalledTimes(3);
});

test('feed error leaves metric chips usable; summary error leaves feed usable', () => {
  mockFeedError = true;
  const { unmount } = mount();
  fireEvent.press(screen.getByTestId('chip-sleep'));
  expect(screen.getByText('detail:sleep')).toBeTruthy();
  fireEvent.press(screen.getByText('Retry'));
  expect(mockFeedRefetch).toHaveBeenCalledTimes(1);
  unmount();
  mockFeedError = false;
  mockSummaryError = true;
  mount();
  fireEvent.press(screen.getByText('Slept well'));
  expect(screen.getByText('detail:sleep')).toBeTruthy();
});

test('nutrition without a profile preserves the alert, profile sheet, and saved refresh', () => {
  mockNutrition = true;
  mount();
  fireEvent.press(screen.getByText('⚠︎ Set up body profile →'));
  fireEvent.press(screen.getByText('profile sheet'));
  expect(mockSummaryRefetch).toHaveBeenCalledTimes(1);
});

test('setup chips keep integration dispatch and task-prefill actions', () => {
  mockRows = [
    { id: 'sleep', status: 'needs_setup', cta: { kind: 'integrations', panel: 'garmin' } },
    { id: 'mood', status: 'no_data', cta: { kind: 'chat-prefill', tag: 'mood', text: 'Log mood' } },
  ] as AgentRow[];
  mount();
  fireEvent.press(screen.getByTestId('chip-sleep'));
  expect(screen.getByText('integration:garmin')).toBeTruthy();
  fireEvent.press(screen.getByTestId('chip-mood'));
  expect(openTask).toHaveBeenCalledWith({ lead: 'mood', prefill: 'Log mood' });
});

test('header settings control has a localized label and opens settings', () => {
  mount();
  fireEvent.press(screen.getByLabelText('Open Settings'));
  expect(screen.getByText('settings')).toBeTruthy();
});
