import { getDocumentAsync } from 'expo-document-picker';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { ChatScreen } from './ChatScreen';

type Msg =
  | { kind: 'error'; id: string; code: string; message: string }
  | { kind: 'user'; id: string; tag?: string; text: string; attachments?: [] }
  | {
      kind: 'assistant';
      id: string;
      agent?: string;
      consulted?: string[];
      text: string;
      streaming: boolean;
      action?: { id: string; summary: string; status: string; expiresAt: string | null };
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

const mockConfirm = jest.fn();
const mockRestore = jest.fn().mockResolvedValue(undefined);
const mockStartNew = jest.fn().mockResolvedValue(undefined);
const mockSetLead = jest.fn().mockResolvedValue(undefined);
let mockInterrupted = false;
let mockLeadAgent: string | null = null;
jest.mock('@/lib/locale', () => ({ appLocale: () => 'ru' }));
jest.mock('./useTask', () => ({
  useTask: () => ({
    messages: mockMessages,
    send: mockSend,
    confirm: mockConfirm,
    reject: jest.fn(),
    restore: mockRestore,
    startNew: mockStartNew,
    setLead: mockSetLead,
    phase: 'idle',
    interrupted: mockInterrupted,
    leadAgent: mockLeadAgent,
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
  mockSend.mockReset().mockResolvedValue(true);
  mockConfirm.mockClear();
  mockSetLead.mockReset().mockResolvedValue(undefined);
  mockRestore.mockReset().mockResolvedValue(undefined);
  mockStartNew.mockClear();
  mockInterrupted = false;
  mockLeadAgent = null;
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

test('autoSend from ?send query param forwards parsed input to useTask.send', async () => {
  mockMessages = [];
  mockSearchParams = { send: '/workout analyze my session' };

  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );

  await waitFor(() => expect(mockSend).toHaveBeenCalledTimes(1));
  expect(mockSend).toHaveBeenCalledWith({
    tag: 'workout',
    text: 'analyze my session',
    attachments: [],
  });
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

test('hold-to-talk puts the transcript in the draft for review without sending', async () => {
  jest.useFakeTimers();
  jest.setSystemTime(0);
  mockMessages = [];
  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );
  await act(async () => {
    fireEvent(screen.getByTestId('ask-mic'), 'pressIn');
  });
  await act(async () => {
    jest.advanceTimersByTime(700);
    fireEvent(screen.getByTestId('ask-mic'), 'pressOut');
  });
  await waitFor(() => expect(screen.getByTestId('ask-input').props.value).toBe('купил хлеб'));
  expect(mockSend).not.toHaveBeenCalled();
  jest.useRealTimers();
});

test('hold-to-talk appends speech to text already in the draft', async () => {
  jest.useFakeTimers();
  jest.setSystemTime(0);
  mockMessages = [];
  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );
  fireEvent.changeText(screen.getByTestId('ask-input'), 'and milk');
  await act(async () => {
    fireEvent(screen.getByTestId('ask-mic'), 'pressIn');
  });
  await act(async () => {
    jest.advanceTimersByTime(700);
    fireEvent(screen.getByTestId('ask-mic'), 'pressOut');
  });
  await waitFor(() =>
    expect(screen.getByTestId('ask-input').props.value).toBe('and milk купил хлеб'),
  );
  expect(mockSend).not.toHaveBeenCalled();
  jest.useRealTimers();
});

const wrap = () =>
  render(
    <ThemeProvider>
      <ChatScreen />
    </ThemeProvider>,
  );
test('renders an action and confirms its id', () => {
  mockMessages = [
    {
      kind: 'assistant',
      id: 'a',
      text: '',
      streaming: false,
      action: { id: 'a1', summary: 'Lamp?', expiresAt: null, status: 'pending' },
    },
  ];
  wrap();
  fireEvent.press(screen.getByTestId('action-confirm'));
  expect(mockConfirm).toHaveBeenCalledWith('a1');
});
test('localizes client errors', () => {
  mockMessages = [{ kind: 'error', id: 'e', code: 'network', message: '' }];
  wrap();
  expect(screen.getByText(/Нет связи с сервером./)).toBeTruthy();
});
test('shows interrupted reply under the user message', () => {
  mockMessages = [{ kind: 'user', id: 'u', text: 'hello' }];
  mockInterrupted = true;
  wrap();
  expect(screen.getByText('Ответ не пришёл — спроси ещё раз.')).toBeTruthy();
});
test('typed new closes the task', async () => {
  wrap();
  fireEvent.changeText(screen.getByTestId('ask-input'), '/new');
  await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
  expect(mockStartNew).toHaveBeenCalledTimes(1);
});

test('sending a tagged message preserves the task lead', async () => {
  wrap();
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep hello');
  await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
  expect(mockSend).toHaveBeenCalledWith({ tag: 'sleep', text: 'hello', attachments: [] });
  expect(mockSetLead).not.toHaveBeenCalledWith(null);
});
test('removing the lead chip clears the server lead', () => {
  wrap();
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep hello');
  fireEvent.press(screen.getByTestId('agent-chip-remove'));
  expect(mockSetLead).toHaveBeenCalledWith(null);
});

test('selecting an agent command sets the task lead immediately', () => {
  wrap();
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep');
  fireEvent.press(screen.getByText('/sleep'));
  expect(mockSetLead).toHaveBeenCalledWith('sleep');
});
test('navigation send waits for restoration', async () => {
  let finish!: () => void;
  mockRestore.mockReturnValue(
    new Promise<void>((resolve) => {
      finish = resolve;
    }),
  );
  mockSearchParams = { send: 'hello' };
  wrap();
  expect(mockSend).not.toHaveBeenCalled();
  await act(async () => finish());
  expect(mockSend).toHaveBeenCalledWith({ text: 'hello', attachments: [] });
});

test('new closes even when the restored task has a lead', async () => {
  mockLeadAgent = 'sleep';
  wrap();
  fireEvent.changeText(screen.getByTestId('ask-input'), '/new');
  await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
  expect(mockStartNew).toHaveBeenCalledTimes(1);
  expect(mockSend).not.toHaveBeenCalled();
});

test('lead-only command sets the lead without posting an empty message', async () => {
  wrap();
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep ');
  await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
  expect(mockSetLead).toHaveBeenCalledWith('sleep');
  expect(mockSend).not.toHaveBeenCalled();
});
test('failed lead selection preserves the typed command chip', async () => {
  mockSetLead.mockRejectedValue(new Error('offline'));
  wrap();
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep ');
  await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
  expect(screen.getByTestId('agent-chip-remove')).toBeTruthy();
  expect(mockSend).not.toHaveBeenCalled();
});
test.each([false, true])(
  'send result %s controls composer text and attachment retention',
  async (success) => {
    mockSend.mockResolvedValue(success);
    (getDocumentAsync as jest.Mock).mockResolvedValueOnce({
      canceled: false,
      assets: [{ uri: 'file:///doc.pdf', name: 'doc.pdf', size: 42 }],
    });
    wrap();
    fireEvent.changeText(screen.getByTestId('ask-input'), 'analyze this');
    await act(async () => fireEvent.press(screen.getByTestId('ask-attach')));
    await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
    expect(screen.getByTestId('ask-input').props.value).toBe(success ? '' : 'analyze this');
    expect(!!screen.queryByText('doc.pdf')).toBe(!success);
    expect(mockSend).toHaveBeenCalledWith({
      tag: undefined,
      text: 'analyze this',
      attachments: [{ uri: 'file:///doc.pdf', name: 'doc.pdf', size: 42, mime: 'application/pdf' }],
    });
  },
);

test.each(['question', 'remove'])(
  'lead-only completion preserves an intervening %s edit',
  async (edit) => {
    let finish!: () => void;
    mockSetLead.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          finish = resolve;
        }),
    );
    wrap();
    fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep ');
    fireEvent.press(screen.getByTestId('ask-send'));
    expect(mockSetLead).toHaveBeenCalledWith('sleep');
    if (edit === 'question')
      fireEvent.changeText(screen.getByTestId('ask-input'), 'How did I sleep?');
    else fireEvent.press(screen.getByTestId('agent-chip-remove'));
    await act(async () => finish());
    if (edit === 'question')
      expect(screen.getByTestId('ask-input').props.value).toBe('How did I sleep?');
    else expect(screen.queryByTestId('agent-chip-remove')).toBeNull();
  },
);
