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
let mockAttention: unknown[] = [];
const mockAttentionRefetch = jest.fn();
const mockDismiss = jest.fn();
jest.mock('./useAttention', () => ({
  useAttention: () => ({
    data: { items: mockAttention, unavailable: [] },
    refetch: mockAttentionRefetch,
  }),
  useDismissAttention: () => ({ mutate: mockDismiss }),
}));
jest.mock('react-native-gesture-handler/ReanimatedSwipeable', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => children,
}));
const attn = (id: string, agent: string, action: { type: string; prompt?: string }) => ({
  agent,
  id,
  level: 'normal',
  rank: 0,
  text: `item ${id}`,
  action,
});
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
  mockAttention = [];
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

test('feed error leaves the agent stack usable; summary error leaves feed usable', () => {
  mockFeedError = true;
  const { unmount } = mount();
  fireEvent.press(screen.getByTestId('agent-stack'));
  expect(screen.getByText('detail:all')).toBeTruthy();
  fireEvent.press(screen.getByText('Retry'));
  expect(mockFeedRefetch).toHaveBeenCalledTimes(1);
  unmount();
  mockFeedError = false;
  mockSummaryError = true;
  mount();
  fireEvent.press(screen.getByText('Slept well'));
  expect(screen.getByText('detail:sleep')).toBeTruthy();
});

test('header settings control has a localized label and opens settings', () => {
  mount();
  fireEvent.press(screen.getByLabelText('Open Settings'));
  expect(screen.getByText('settings')).toBeTruthy();
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

test('the now block shows on today and hides on a previous day', () => {
  mockAttention = [attn('a1', 'sleep', { type: 'agent' })];
  mount();
  expect(screen.getByText('item a1')).toBeTruthy();
  fireEvent.press(screen.getByLabelText('Previous day'));
  expect(screen.queryByText('item a1')).toBeNull();
});

test('a task item opens the task sheet with the prompt prefilled', () => {
  mockAttention = [attn('t1', 'workout', { type: 'task', prompt: 'Help me plan a workout' })];
  mount();
  fireEvent.press(screen.getByText('item t1'));
  expect(openTask).toHaveBeenCalledWith({ lead: 'workout', prefill: 'Help me plan a workout' });
});

test('a profile item opens the body profile sheet and saving refetches attention', () => {
  mockAttention = [attn('p1', 'nutrition', { type: 'profile' })];
  mount();
  fireEvent.press(screen.getByText('item p1'));
  fireEvent.press(screen.getByText('profile sheet'));
  expect(mockAttentionRefetch).toHaveBeenCalled();
});

test('an agent item opens the pager', () => {
  mockAttention = [attn('k1', 'kitchen', { type: 'agent' })];
  mockRows = [{ id: 'kitchen', status: 'ready', cta: null }] as unknown as AgentRow[];
  mount();
  fireEvent.press(screen.getByText('item k1'));
  expect(screen.getByText('detail:kitchen')).toBeTruthy();
});

test('the agent stack opens the grid', () => {
  mount();
  fireEvent.press(screen.getByTestId('agent-stack'));
  expect(screen.getByText('detail:all')).toBeTruthy();
});
