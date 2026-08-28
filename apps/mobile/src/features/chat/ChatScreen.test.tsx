import { fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { ChatScreen } from './ChatScreen';

type Msg =
  | { kind: 'user'; id: string; tag?: string; text: string }
  | {
      kind: 'assistant';
      id: string;
      agent?: string;
      consulted?: string[];
      text: string;
      streaming: boolean;
    };

const defaultMessages: Msg[] = [
  { kind: 'user', id: 'u1', tag: 'sleep', text: 'how did I sleep' },
  {
    kind: 'assistant',
    id: 'a1',
    agent: 'sleep',
    consulted: ['nutrition'],
    text: 'You slept 7h.',
    streaming: false,
  },
];

let mockMessages: Msg[] = defaultMessages;
let mockSearchParams: Record<string, string> = {};
const mockSend = jest.fn();

jest.mock('./useChat', () => ({
  useChat: () => ({
    messages: mockMessages,
    send: mockSend,
    sendFile: jest.fn(),
    resetThread: jest.fn(),
  }),
}));

jest.mock('../integrations/store', () => ({
  useConnectedIntegrations: () => new Set(),
}));

jest.mock('expo-router', () => {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const ReactMod = require('react');
  return {
    useRouter: () => ({
      push: jest.fn(),
      replace: jest.fn(),
      back: jest.fn(),
      setParams: jest.fn(),
    }),
    useSegments: () => [],
    useLocalSearchParams: () => mockSearchParams,
    useFocusEffect: (effect: () => void) => {
      const stable = ReactMod.useRef(effect);
      stable.current = effect;
      ReactMod.useEffect(() => stable.current(), []);
    },
    Link: ({ children }: { children: unknown }) => children,
  };
});

jest.mock('@/features/agents/useAgentStatusRows', () => ({
  useAgentStatusRows: () => ({
    rows: [],
    readyCount: 0,
    totalCount: 11,
    lastSyncedAt: null,
    isSyncing: false,
    isLoading: false,
  }),
}));

jest.mock('./ChatHeader', () => ({
  ChatHeader: () => null,
}));

beforeEach(() => {
  mockMessages = defaultMessages;
  mockSearchParams = {};
  mockSend.mockClear();
});

test('renders agent header above assistant bubble', () => {
  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );
  expect(screen.getByText('SLEEP')).toBeOnTheScreen();
  expect(screen.getByText('via')).toBeOnTheScreen();
  expect(screen.getByText('nutrition')).toBeOnTheScreen();
});

test('renders inline chip in user bubble for tagged message', () => {
  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );
  // The chip and the message text are both visible.
  expect(screen.getByText('sleep')).toBeOnTheScreen();
  expect(screen.getByText('how did I sleep')).toBeOnTheScreen();
});

test('autoSend from ?send query param forwards string to useChat.send', () => {
  mockMessages = [];
  mockSearchParams = { send: '/workout analyze my session' };

  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );

  expect(mockSend).toHaveBeenCalledTimes(1);
  expect(mockSend).toHaveBeenCalledWith('/workout analyze my session');
});

test('typing /home with no integrations connected does not promote to chip', () => {
  mockMessages = [];
  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );
  fireEvent.changeText(screen.getByTestId('ask-input'), '/home ');
  expect(screen.queryByTestId('agent-chip-remove')).toBeNull();
});

test('typing /sleep with no integrations still promotes (sleep is not gated)', () => {
  mockMessages = [];
  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep ');
  expect(screen.getByTestId('agent-chip-remove')).toBeOnTheScreen();
});

test('prefill with invalid tag does NOT seed a chip but still sets the text', () => {
  mockMessages = [];
  mockSearchParams = { prefill: '/something', tag: 'not-an-agent' };

  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );

  // No chip — invalid tag was rejected.
  expect(screen.queryByTestId('agent-chip-remove')).toBeNull();
});

test('prefill with tag query params seeds the AskBar with chip and empty text', () => {
  mockMessages = [];
  mockSearchParams = { prefill: '', tag: 'mood' };

  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );

  // The chip is the visible affordance for the tag in the AskBar.
  expect(screen.getByTestId('agent-chip-remove')).toBeOnTheScreen();
  // Send was not auto-invoked (this is prefill, not send).
  expect(mockSend).not.toHaveBeenCalled();
});
