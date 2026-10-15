import { ThemeProvider } from '@life-agents/ui';
import React from 'react';
import {
  act,
  fireEvent,
  render as nativeRender,
  screen,
  waitFor,
} from '@testing-library/react-native';
import * as ImagePicker from 'expo-image-picker';
import { TaskConversation, type TaskChat } from './TaskConversation';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('../integrations/store', () => ({ useConnectedIntegrations: () => new Set() }));
let mockTranscript: (text: string) => void = () => undefined;
jest.mock('../voice/useVoiceInput', () => ({
  useVoiceInput: (opts: { onTranscript: (t: string) => void }) => {
    mockTranscript = opts.onTranscript;
    return {
      state: 'idle',
      seconds: 0,
      start: jest.fn(),
      stop: jest.fn(),
      cancel: jest.fn(),
      level: 0,
    };
  },
}));
jest.mock('react-native/Libraries/ActionSheetIOS/ActionSheetIOS', () => ({
  __esModule: true,
  default: { showActionSheetWithOptions: (_o: unknown, cb: (i: number) => void) => cb(1) },
}));

function chat(over: Partial<TaskChat> = {}): TaskChat {
  return {
    taskId: null,
    leadAgent: null,
    messages: [],
    pendingAction: null,
    phase: 'idle',
    interrupted: false,
    restore: jest.fn(),
    send: jest.fn(async () => true),
    setLead: jest.fn(async () => undefined),
    confirm: jest.fn(),
    reject: jest.fn(),
    close: jest.fn(),
    startNew: jest.fn(),
    ...over,
  } as TaskChat;
}

test('quick chips set the lead and hide after the first message', async () => {
  const c = chat();
  const { rerender } = render(<TaskConversation chat={c} />);
  fireEvent.press(screen.getByText('🍽 Food'));
  expect(c.setLead).toHaveBeenCalledWith('nutrition');
  rerender(
    <ThemeProvider>
      <TaskConversation
        chat={chat({ messages: [{ kind: 'user', id: 'u1', text: 'hi', attachments: [] }] })}
      />
    </ThemeProvider>,
  );
  expect(screen.queryByText('🍽 Food')).toBeNull();
});

test('a command sets the lead; a leading tag in text sends with it', async () => {
  const c = chat();
  render(<TaskConversation chat={c} />);
  const input = screen.getByTestId('ask-input');
  fireEvent.changeText(input, '/kit');
  fireEvent.press(screen.getByText('/kitchen'));
  expect(c.setLead).toHaveBeenCalledWith('kitchen');
  fireEvent.changeText(input, '/workout analyze');
  fireEvent.press(screen.getByTestId('ask-send'));
  await waitFor(() =>
    expect(c.send).toHaveBeenCalledWith({ text: 'analyze', tag: 'workout', attachments: [] }),
  );
});

test('the lead chip clears the lead', () => {
  const c = chat({ taskId: 't1', leadAgent: 'sleep' });
  render(<TaskConversation chat={c} />);
  fireEvent.press(screen.getByLabelText('Remove lead agent'));
  expect(c.setLead).toHaveBeenCalledWith(null);
});

test('a voice transcript is sent at once with the pending attachments', async () => {
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValueOnce({
    canceled: false,
    assets: [{ uri: 'file:///p.jpg', fileName: 'p.jpg', mimeType: 'image/jpeg', fileSize: 10 }],
  });
  const c = chat();
  render(<TaskConversation chat={c} />);
  fireEvent.press(screen.getByTestId('ask-attach'));
  await screen.findByText('p.jpg');
  await act(async () => mockTranscript('что на ужин'));
  await waitFor(() =>
    expect(c.send).toHaveBeenCalledWith({
      text: 'что на ужин',
      attachments: [{ uri: 'file:///p.jpg', name: 'p.jpg', mime: 'image/jpeg', size: 10 }],
    }),
  );
});

test('an attachment over the limit is refused with the reason', async () => {
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValueOnce({
    canceled: false,
    assets: [{ uri: 'file:///h.heic', fileName: 'h.heic', mimeType: 'image/heic', fileSize: 10 }],
  });
  const c = chat();
  render(<TaskConversation chat={c} />);
  fireEvent.press(screen.getByTestId('ask-attach'));

  expect(await screen.findByText('Only JPEG, PNG, WebP photos and PDF files.')).toBeTruthy();
  expect(c.send).not.toHaveBeenCalled();
});

test('a network error offers retry with the last message', () => {
  const c = chat({
    taskId: 't1',
    messages: [
      { kind: 'user', id: 'u1', text: 'hi', attachments: [] },
      { kind: 'error', id: 'e1', code: 'network', message: '' },
    ],
  });
  render(<TaskConversation chat={c} />);
  fireEvent.press(screen.getByText('⟳ Retry'));
  expect(c.send).toHaveBeenCalledWith({ text: 'hi', attachments: [] });
});

test('a seed fills the draft; voice notes caption their bubble', () => {
  const c = chat({ messages: [{ kind: 'user', id: 'u1', text: 'съели курицу', attachments: [] }] });
  render(
    <TaskConversation
      chat={c}
      seed={{ key: 1, text: 'draft' }}
      voiceNotes={[{ text: 'съели курицу', seconds: 6 }]}
    />,
  );
  expect(screen.getByDisplayValue('draft')).toBeTruthy();
  expect(screen.getByText('🎙 0:06')).toBeTruthy();
});

function render(ui: React.ReactElement) {
  return nativeRender(<ThemeProvider>{ui}</ThemeProvider>);
}

const file = { uri: 'file:///a.jpg', name: 'a.jpg', mime: 'image/jpeg', size: 10 };
test.each([false, 'reject'])(
  'failed send %s retains text/files and offers retry',
  async (failure) => {
    const c = chat({
      send: jest
        .fn()
        .mockImplementationOnce(() =>
          failure === false ? Promise.resolve(false) : Promise.reject(new Error('offline')),
        )
        .mockResolvedValue(true),
    });
    render(<TaskConversation chat={c} seed={{ key: 1, text: 'look', attachments: [file] }} />);
    fireEvent.press(screen.getByTestId('ask-send'));
    await screen.findByText('⟳ Retry');
    expect(screen.getByDisplayValue('look')).toBeTruthy();
    expect(screen.getByText('a.jpg')).toBeTruthy();
    await act(async () => fireEvent.press(screen.getByText('⟳ Retry')));
    await waitFor(() => expect(screen.queryByDisplayValue('look')).toBeNull());
    expect(c.send).toHaveBeenLastCalledWith({ text: 'look', attachments: [file] });
  },
);
test('completion preserves newer draft and files', async () => {
  let finish!: (v: boolean) => void;
  const c = chat({
    send: jest.fn(
      () =>
        new Promise<boolean>((r) => {
          finish = r;
        }),
    ),
  });
  const view = render(
    <TaskConversation chat={c} seed={{ key: 1, text: 'old', attachments: [file] }} />,
  );
  fireEvent.press(screen.getByTestId('ask-send'));
  fireEvent.changeText(screen.getByTestId('ask-input'), 'new');
  view.rerender(
    <ThemeProvider>
      <TaskConversation chat={c} seed={{ key: 2, attachments: [{ ...file, name: 'b.jpg' }] }} />
    </ThemeProvider>,
  );
  await act(async () => finish(true));
  expect(screen.getByDisplayValue('new')).toBeTruthy();
  expect(screen.getByText('b.jpg')).toBeTruthy();
});
test('seed validates all incoming plus existing files without truncation', () => {
  const c = chat();
  const view = render(<TaskConversation chat={c} seed={{ key: 1, attachments: [file] }} />);
  view.rerender(
    <ThemeProvider>
      <TaskConversation
        chat={c}
        seed={{
          key: 2,
          attachments: Array.from({ length: 4 }, () => ({ ...file, name: 'b.jpg' })),
        }}
      />
    </ThemeProvider>,
  );
  expect(screen.getByText('Up to 4 files per message.')).toBeTruthy();
  expect(screen.queryByText('b.jpg')).toBeNull();
  expect(screen.getByText('a.jpg')).toBeTruthy();
});
test.each(['chip', 'command', 'clear'])('lead %s errors are localized notices', async (kind) => {
  const c = chat({
    leadAgent: kind === 'clear' ? 'sleep' : null,
    setLead: jest.fn().mockRejectedValue(new Error('offline')),
  });
  render(<TaskConversation chat={c} />);
  if (kind === 'clear') fireEvent.press(screen.getByLabelText('Remove lead agent'));
  else if (kind === 'chip') fireEvent.press(screen.getByText('🍽 Food'));
  else {
    fireEvent.changeText(screen.getByTestId('ask-input'), '/kit');
    fireEvent.press(screen.getByText('/kitchen'));
  }
  expect(await screen.findByText(/No connection/)).toBeTruthy();
});
test('renders pending action, header, attachments, error and missing reply', () => {
  const c = chat({
    interrupted: true,
    messages: [
      {
        kind: 'user',
        id: 'u',
        text: 'hello',
        tag: 'sleep',
        attachments: [{ kind: 'document', name: 'report.pdf', mime: 'application/pdf', size: 1 }],
      },
      {
        kind: 'assistant',
        id: 'a',
        text: 'answer',
        streaming: false,
        agent: 'sleep',
        consulted: ['nutrition'],
        action: { id: 'a1', summary: 'Lamp?', status: 'pending', expiresAt: null },
      },
      { kind: 'error', id: 'e', code: 'network', message: '' },
    ],
  });
  render(<TaskConversation chat={c} />);
  fireEvent.press(screen.getByTestId('action-confirm'));
  expect(c.confirm).toHaveBeenCalledWith('a1');
  expect(screen.getByText('SLEEP')).toBeTruthy();
  expect(screen.getByText(/report.pdf/)).toBeTruthy();
  expect(screen.getByText(/No connection/)).toBeTruthy();
  expect(screen.getByText(/reply|Reply/)).toBeTruthy();
});

import { useTask } from '../chat/useTask';
import type { TasksApi } from '../chat/tasksApi';
import * as SecureStore from 'expo-secure-store';
test('real useTask waits for delayed SSE failure and retries original files in the same task', async () => {
  await SecureStore.deleteItemAsync('open_task_id');
  let release!: () => void;
  const barrier = new Promise<void>((resolve) => {
    release = resolve;
  });
  async function* failedEvents() {
    await barrier;
    yield { type: 'http_error' as const, code: 'network' };
  }
  async function* successfulEvents() {
    yield { type: 'finished' as const };
  }
  const api: TasksApi = {
    open: jest.fn(async () => ({ id: 'task-retry', leadAgent: null })),
    read: jest.fn(async () => null),
    setLead: jest.fn(async (id, leadAgent) => ({ id, leadAgent })),
    close: jest.fn(async () => undefined),
    resolve: jest.fn(async () => ({ status: 'applied' as const, message: '' })),
    post: jest
      .fn()
      .mockReturnValueOnce({ events: failedEvents(), abort: jest.fn() })
      .mockReturnValueOnce({ events: successfulEvents(), abort: jest.fn() }),
  };
  function Conversation() {
    const c = useTask(api);
    return <TaskConversation chat={c} seed={{ key: 1, text: 'look', attachments: [file] }} />;
  }
  render(<Conversation />);
  fireEvent.press(screen.getByTestId('ask-send'));
  await waitFor(() => expect(screen.getByTestId('ask-input').props.editable).toBe(false));
  expect(screen.getByDisplayValue('look')).toBeTruthy();
  expect(screen.getByText('a.jpg')).toBeTruthy();
  await act(async () => release());
  await screen.findByText('⟳ Retry');
  await act(async () => fireEvent.press(screen.getByText('⟳ Retry')));
  await waitFor(() => expect(screen.queryByDisplayValue('look')).toBeNull());
  expect(api.open).toHaveBeenCalledTimes(1);
  expect(api.post).toHaveBeenLastCalledWith('task-retry', { text: 'look', attachments: [file] });
});
test.each(['/workout analyze', ' /workout analyze  '])(
  'successful tagged send clears composer %s',
  async (draft) => {
    render(<TaskConversation chat={chat()} />);
    fireEvent.changeText(screen.getByTestId('ask-input'), draft);
    await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
    expect(screen.queryByDisplayValue(draft)).toBeNull();
  },
);
test('lead-only input sets lead without sending an empty turn', async () => {
  const c = chat();
  render(<TaskConversation chat={c} />);
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep ');
  fireEvent.press(screen.getByTestId('ask-send'));
  await waitFor(() => expect(c.setLead).toHaveBeenCalledWith('sleep'));
  expect(c.send).not.toHaveBeenCalled();
});
test('retrying a failed turn preserves a newer unsent draft', async () => {
  const c = chat({ send: jest.fn().mockResolvedValueOnce(false).mockResolvedValue(true) });
  render(<TaskConversation chat={c} seed={{ key: 1, text: 'old' }} />);
  await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
  fireEvent.changeText(screen.getByTestId('ask-input'), 'new');
  await act(async () => fireEvent.press(screen.getByText('⟳ Retry')));
  expect(screen.getByDisplayValue('new')).toBeTruthy();
});
test('retry remains actionable if failure occurred before a user bubble was created', async () => {
  const c = chat({ send: jest.fn().mockResolvedValueOnce(false).mockResolvedValue(true) });
  const view = render(<TaskConversation chat={c} seed={{ key: 1, text: 'old' }} />);
  await act(async () => fireEvent.press(screen.getByTestId('ask-send')));
  view.rerender(
    <ThemeProvider>
      <TaskConversation
        chat={{ ...c, messages: [{ kind: 'error', id: 'e', code: 'network', message: '' }] }}
      />
    </ThemeProvider>,
  );
  await act(async () => fireEvent.press(screen.getByText('⟳ Retry')));
  expect(c.send).toHaveBeenCalledTimes(2);
});
test('no household error explains how to join a home', () => {
  render(
    <TaskConversation
      chat={chat({ messages: [{ kind: 'error', id: 'e', code: 'no_household', message: '' }] })}
    />,
  );
  expect(screen.getByText(/Join or create a home first — see the House tab\./)).toBeTruthy();
});

import { Alert, Platform } from 'react-native';
test('Android source chooser exposes three sources and cancellable dismissal', async () => {
  const original = Platform.OS;
  Object.defineProperty(Platform, 'OS', { configurable: true, value: 'android' });
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
  const picker = ImagePicker.launchImageLibraryAsync as jest.Mock;
  const before = picker.mock.calls.length;
  try {
    render(<TaskConversation chat={chat()} />);
    await act(async () => fireEvent.press(screen.getByTestId('ask-attach')));
    const [title, , buttons, options] = alert.mock.calls[0]!;
    expect(title).toBe('Attach');
    expect(buttons?.map((b) => b.text)).toEqual(['Camera', 'Photo library', 'File (PDF)']);
    expect(options?.cancelable).toBe(true);
    expect(options?.onDismiss).toEqual(expect.any(Function));
    await act(async () => options?.onDismiss?.());
    expect(picker.mock.calls.length).toBe(before);
    expect(screen.queryByText('a.jpg')).toBeNull();
    picker.mockResolvedValueOnce({
      canceled: false,
      assets: [
        {
          uri: 'file:///android.jpg',
          fileName: 'android.jpg',
          mimeType: 'image/jpeg',
          fileSize: 1,
        },
      ],
    });
    await act(async () => fireEvent.press(screen.getByTestId('ask-attach')));
    await act(async () => alert.mock.calls[1]?.[2]?.[1]?.onPress?.());
    expect(await screen.findByText('android.jpg')).toBeTruthy();
  } finally {
    alert.mockRestore();
    Object.defineProperty(Platform, 'OS', { configurable: true, value: original });
  }
});

test('E2E completion marker requires the latest nonempty assistant reply after streaming', () => {
  const reply = {
    kind: 'assistant' as const,
    id: 'a1',
    text: 'Added milk',
    streaming: false,
    completed: true,
  };
  const { rerender } = render(<TaskConversation chat={chat({ messages: [reply] })} />);
  expect(screen.getByTestId('task-assistant-complete').props.accessibilityLabel).toBe('Added milk');
  const update = (messages: TaskChat['messages'], phase: TaskChat['phase'] = 'idle') =>
    rerender(
      <ThemeProvider>
        <TaskConversation chat={chat({ messages, phase })} />
      </ThemeProvider>,
    );
  update([{ ...reply, streaming: true }], 'streaming');
  expect(screen.queryByTestId('task-assistant-complete')).toBeNull();
  update([{ ...reply, completed: undefined }]);
  expect(screen.queryByTestId('task-assistant-complete')).toBeNull();
  update([{ ...reply, completed: false }]);
  expect(screen.queryByTestId('task-assistant-complete')).toBeNull();
  update([{ ...reply, text: '   ' }]);
  expect(screen.queryByTestId('task-assistant-complete')).toBeNull();
  update([reply, { kind: 'user', id: 'u2', text: 'Next request', attachments: [] }]);
  expect(screen.queryByTestId('task-assistant-complete')).toBeNull();
});
