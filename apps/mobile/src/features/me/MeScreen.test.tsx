import React from 'react';
import { Text, Pressable, ScrollView } from 'react-native';
import { ThemeProvider } from '@life-agents/ui';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { MeScreen } from './MeScreen';
import { feedDay } from './useDayFeed';
import { computeAgentStatus, type AgentRow } from '../agents/agentStatusRules';
import { dispatchTilePress } from '../agents/agentTileDispatch';
import { openTask } from '../task/sheetStore';

const mockSummaryRefetch = jest.fn();
const mockFeedRefetch = jest.fn();
const mockRefresh = jest.fn();
const mockPush = jest.fn();
const mockRouter = { push: mockPush, setParams: (p: unknown) => mockSetParams(p) };
let mockFocus: (() => void) | undefined;
let mockSummaryError = false;
let mockFeedError = false;
let mockNutrition = false;
let mockBodyFeed = false;
let mockRows: AgentRow[] = [];
jest.mock('../agents/agentTileDispatch', () => ({
  dispatchTilePress: jest.fn(jest.requireActual('../agents/agentTileDispatch').dispatchTilePress),
}));
jest.mock('../task/sheetStore', () => ({ openTask: jest.fn() }));
const mockUseDayFeed = jest.fn();
let mockParams: { agent?: string } = {};
const mockSetParams = jest.fn();
jest.mock('expo-router', () => ({
  useRouter: () => mockRouter,
  useLocalSearchParams: () => mockParams,
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
                agent: mockBodyFeed ? 'body' : 'sleep',
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
jest.mock('./AgentPagerSheet', () => ({
  PAGES: ['all', 'sleep', 'kitchen'],
  AgentPagerSheet: ({ start }: { start: string | null }) =>
    start ? <Text>{`detail:${start}`}</Text> : null,
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
  mockBodyFeed = false;
  mockRows = [];
  mockParams = {};
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
    {
      id: 'mood',
      status: 'needs_setup',
      cta: { kind: 'chat-prefill', tag: 'mood', text: 'Log mood' },
    },
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

test('all chip opens the grid', () => {
  mount();
  fireEvent.press(screen.getByTestId('chip-all'));
  expect(screen.getByText('detail:all')).toBeTruthy();
});

test('body row goes through tile dispatch', () => {
  mockRows = [
    { id: 'body', status: 'needs_setup', cta: { kind: 'integrations', panel: 'apple-health' } },
  ] as AgentRow[];
  mount();
  fireEvent.press(screen.getByTestId('chip-body'));
  expect(dispatchTilePress).toHaveBeenCalledWith(
    mockRows[0],
    expect.objectContaining({ openDetail: expect.any(Function) }),
  );
});

jest.mock('../home/AgentDetailContent', () => ({
  AgentDetailContent: ({
    agentId,
    onAction,
  }: {
    agentId: string;
    onAction: (text: string) => void;
  }) => (
    <Pressable onPress={() => onAction('existing action')}>
      <Text>{`standalone:${agentId}`}</Text>
    </Pressable>
  ),
}));
test.each(['body', 'home'] as const)(
  'real ready %s status dispatch opens usable separate details',
  (id) => {
    const status = computeAgentStatus(id, {
      integrations: new Set(['ha']),
      peerOnline: new Map(),
      meProfile: null,
      summary: {
        agents: [
          {
            agent: 'body',
            label: 'Body',
            metric: '70 kg',
            detail: null,
            tint: 'neutral',
            progress: null,
          },
        ],
        unavailable: [],
      },
    });
    expect(status).toEqual({ status: 'ready', hint: null, cta: null });
    mockRows = [{ id, description: '', ...status }];
    mount();
    fireEvent.press(screen.getByTestId(`chip-${id}`));
    expect(screen.getByText(`standalone:${id}`)).toBeTruthy();
    expect(screen.queryByText(`detail:${id}`)).toBeNull();
    fireEvent.press(screen.getByText(`standalone:${id}`));
    expect(openTask).toHaveBeenCalledWith({ lead: id, send: 'existing action' });
  },
);
test('a Body feed entry opens the separate usable Body destination', () => {
  mockBodyFeed = true;
  mockRows = [
    {
      id: 'body',
      description: '',
      ...computeAgentStatus('body', {
        integrations: new Set(),
        peerOnline: new Map(),
        meProfile: null,
        summary: {
          agents: [
            {
              agent: 'body',
              label: 'Body',
              metric: '70 kg',
              detail: null,
              tint: 'neutral',
              progress: null,
            },
          ],
          unavailable: [],
        },
      }),
    },
  ];
  mount();
  fireEvent.press(screen.getByText('Slept well'));
  expect(screen.getByText('standalone:body')).toBeTruthy();
  expect(screen.queryByText('detail:all')).toBeNull();
});

test('?agent=kitchen opens the agent sheet on the kitchen page', () => {
  mockParams = { agent: 'kitchen' };
  mount();
  expect(screen.getByText('detail:kitchen')).toBeTruthy();
  expect(mockSetParams).toHaveBeenCalledWith({ agent: undefined });
});
