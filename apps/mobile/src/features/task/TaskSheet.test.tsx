import { ThemeProvider } from '@life-agents/ui';
import React from 'react';
import * as SecureStore from 'expo-secure-store';
import { Alert, BackHandler } from 'react-native';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { fakeTasksApi } from '@/features/chat/fakeTasksApi';
import { saveOpenTaskId } from '@/features/chat/taskStorage';
import { TaskBusyError } from '@/features/chat/tasksApi';
import { openTask, useTaskSheet } from './sheetStore';
import { TaskSheet } from './TaskSheet';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('../integrations/store', () => ({ useConnectedIntegrations: () => new Set() }));
let mockApi = fakeTasksApi();
jest.mock('@/features/chat/tasksApi', () => ({
  ...jest.requireActual('@/features/chat/tasksApi'),
  defaultTasksApi: () => mockApi,
}));

beforeEach(async () => {
  jest.restoreAllMocks();
  await SecureStore.deleteItemAsync('open_task_id');
  useTaskSheet.getState().hide();
  mockApi = fakeTasksApi();
  useTaskSheet.setState({ visible: false, origin: null, pending: null });
});

test('an empty sheet closes without asking and without requests', async () => {
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask());
  fireEvent.press(await screen.findByTestId('task-close'));
  expect(useTaskSheet.getState().visible).toBe(false);
  expect(mockApi.open).not.toHaveBeenCalled();
  expect(mockApi.close).not.toHaveBeenCalled();
});

test('a request while a task is open reuses it', async () => {
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ send: 'Купил молоко' }));
  await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(1));
  // the sheet is still open (a non-empty task cannot be hidden); a chip, share or agent action arrives
  act(() => openTask({ lead: 'kitchen', send: 'а что с сыром?' }));
  await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(2));
  expect(mockApi.open).toHaveBeenCalledTimes(1);
  expect(mockApi.setLead).toHaveBeenCalledWith('t1', 'kitchen');
  expect((mockApi.post as jest.Mock).mock.calls.map((c) => c[0])).toEqual(['t1', 't1']);
});

test('ending a task asks, deletes and hides', async () => {
  const alert = jest
    .spyOn(Alert, 'alert')
    .mockImplementation((_t, _m, buttons) =>
      buttons?.find((b) => b.style === 'destructive')?.onPress?.(),
    );
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ send: 'hi' }));
  await waitFor(() => expect(mockApi.post).toHaveBeenCalled());
  fireEvent.press(screen.getByTestId('task-close'));
  await waitFor(() => expect(mockApi.close).toHaveBeenCalledWith('t1'));
  expect(alert).toHaveBeenCalledWith('End task?', expect.any(String), expect.any(Array));
  expect(useTaskSheet.getState().visible).toBe(false);
});

test('a busy task stays open with a notice', async () => {
  mockApi = fakeTasksApi({
    close: jest.fn(async () => {
      throw new TaskBusyError('task_busy');
    }),
  });
  jest
    .spyOn(Alert, 'alert')
    .mockImplementation((_t, _m, buttons) =>
      buttons?.find((b) => b.style === 'destructive')?.onPress?.(),
    );
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ send: 'hi' }));
  await waitFor(() => expect(mockApi.post).toHaveBeenCalled());
  fireEvent.press(screen.getByTestId('task-close'));
  expect(
    await screen.findByText('Still answering — try again in a second', {}, { timeout: 3000 }),
  ).toBeTruthy();
  expect(useTaskSheet.getState().visible).toBe(true);
});

test('an open task is restored and shown at launch', async () => {
  await saveOpenTaskId('t9');
  mockApi = fakeTasksApi({
    read: jest.fn(async () => ({
      task: { id: 't9', leadAgent: null },
      messages: [{ role: 'user' as const, seq: 1, text: 'вчерашнее', attachments: [] }],
      pendingAction: null,
    })),
  });
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  expect(await screen.findByText('вчерашнее')).toBeTruthy();
  expect(useTaskSheet.getState().visible).toBe(true);
});

test('a voice request sends the transcript and captions it', async () => {
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ voice: { text: 'съели курицу', seconds: 6 } }));
  await waitFor(() =>
    expect(mockApi.post).toHaveBeenCalledWith('t1', { text: 'съели курицу', attachments: [] }),
  );
  expect(await screen.findByText('🎙 0:06')).toBeTruthy();
});

test('simultaneous requests wait for the active stream and retain FIFO order', async () => {
  let finish!: () => void;
  const waiting = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const post = jest
    .fn()
    .mockImplementationOnce(() => ({
      events: (async function* () {
        await waiting;
        yield { type: 'finished' as const };
      })(),
      abort: jest.fn(),
    }))
    .mockImplementation(() => ({
      events: (async function* () {
        yield { type: 'finished' as const };
      })(),
      abort: jest.fn(),
    }));
  mockApi = fakeTasksApi({ post });
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ send: 'first' }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  act(() => {
    openTask({ lead: 'kitchen', send: 'second' });
    openTask({ send: 'third' });
    openTask();
  });
  expect(post).toHaveBeenCalledTimes(1);
  expect(mockApi.setLead).not.toHaveBeenCalled();
  await act(async () => finish());
  await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
  expect(post.mock.calls.map((call) => call[1].text)).toEqual(['first', 'second', 'third']);
  expect(mockApi.open).toHaveBeenCalledTimes(1);
  expect(mockApi.setLead).toHaveBeenCalledWith('t1', 'kitchen');
  expect(useTaskSheet.getState().pending).toBeNull();
});

test('failed restore keeps incoming work behind the saved identity until retry succeeds', async () => {
  await saveOpenTaskId('saved');
  mockApi = fakeTasksApi({
    read: jest
      .fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue({
        task: { id: 'saved', leadAgent: null },
        messages: [],
        pendingAction: null,
      }),
  });
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ send: 'queued' }));
  expect(await screen.findByText('Could not restore task')).toBeTruthy();
  expect(mockApi.open).not.toHaveBeenCalled();
  expect(mockApi.post).not.toHaveBeenCalled();
  expect(await SecureStore.getItemAsync('open_task_id')).toBe('saved');
  fireEvent.press(screen.getByText('Retry'));
  await waitFor(() =>
    expect(mockApi.post).toHaveBeenCalledWith('saved', { text: 'queued', attachments: [] }),
  );
  expect(mockApi.open).not.toHaveBeenCalled();
});

test('closing an empty seeded draft clears it before the next open', async () => {
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ prefill: 'old draft' }));
  expect(await screen.findByDisplayValue('old draft')).toBeTruthy();
  fireEvent.press(screen.getByTestId('task-close'));
  await waitFor(() => expect(useTaskSheet.getState().visible).toBe(false));
  act(() => openTask());
  await screen.findByTestId('task-close');
  expect(screen.queryByDisplayValue('old draft')).toBeNull();
  expect(mockApi.open).not.toHaveBeenCalled();
});

test('Android hardware back asks before ending an existing task', async () => {
  let back: (() => boolean) | undefined;
  jest
    .spyOn(BackHandler, 'addEventListener')
    .mockImplementation((_name: unknown, callback: unknown) => {
      back = callback as () => boolean;
      return { remove: jest.fn() };
    });
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ send: 'hello' }));
  await waitFor(() => expect(mockApi.post).toHaveBeenCalled());
  act(() => expect(back?.()).toBe(true));
  expect(alert).toHaveBeenCalledWith('End task?', expect.any(String), expect.any(Array));
  expect(useTaskSheet.getState().visible).toBe(true);
  expect(mockApi.close).not.toHaveBeenCalled();
});

test('ending a task after failed restore permits a fresh empty sheet', async () => {
  await saveOpenTaskId('saved');
  mockApi = fakeTasksApi({
    read: jest.fn(async () => {
      throw new Error('offline');
    }),
  });
  jest
    .spyOn(Alert, 'alert')
    .mockImplementation((_t, _m, buttons) =>
      buttons?.find((b) => b.style === 'destructive')?.onPress?.(),
    );
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  await screen.findByText('Could not restore task');
  fireEvent.press(screen.getByTestId('task-restore-close'));
  await waitFor(() => expect(useTaskSheet.getState().visible).toBe(false));
  act(() => openTask({ send: 'fresh' }));
  await waitFor(() =>
    expect(mockApi.post).toHaveBeenCalledWith('t1', { text: 'fresh', attachments: [] }),
  );
  expect(mockApi.close).toHaveBeenCalledWith('saved');
});

test('a failed queued send waits for explicit retry and preserves its payload', async () => {
  mockApi = fakeTasksApi({
    post: jest
      .fn()
      .mockImplementationOnce(() => ({
        events: (async function* () {
          yield { type: 'http_error', code: 'network' };
        })(),
        abort: jest.fn(),
      }))
      .mockImplementation(() => ({
        events: (async function* () {
          yield { type: 'finished' };
        })(),
        abort: jest.fn(),
      })),
  });
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ send: 'retry this' }));
  await screen.findByText('Retry');
  expect(mockApi.post).toHaveBeenCalledTimes(1);
  expect(useTaskSheet.getState().pending).toEqual({ send: 'retry this' });
  fireEvent.press(screen.getByText('Retry'));
  await waitFor(() => expect(mockApi.post).toHaveBeenCalledTimes(2));
  expect((mockApi.post as jest.Mock).mock.calls.map((c) => c[1].text)).toEqual([
    'retry this',
    'retry this',
  ]);
  await waitFor(() => expect(useTaskSheet.getState().pending).toBeNull());
});

test('closing during delayed restoration cannot reopen the sheet', async () => {
  await saveOpenTaskId('saved');
  let resolve!: (value: null) => void;
  mockApi = fakeTasksApi({
    read: jest.fn(
      () =>
        new Promise<null>((r) => {
          resolve = r;
        }),
    ),
  });
  jest
    .spyOn(Alert, 'alert')
    .mockImplementation((_t, _m, buttons) =>
      buttons?.find((b) => b.style === 'destructive')?.onPress?.(),
    );
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ send: 'never send' }));
  await waitFor(() => expect(mockApi.read).toHaveBeenCalled());
  fireEvent.press(screen.getByTestId('task-restore-close'));
  await act(async () => resolve(null));
  await waitFor(() => expect(useTaskSheet.getState().visible).toBe(false));
  expect(mockApi.post).not.toHaveBeenCalled();
  expect(useTaskSheet.getState().pending).toBeNull();
});

test('a busy close during delayed restore exposes a working restore retry for the same task', async () => {
  await saveOpenTaskId('saved');
  let finish!: () => void;
  const waiting = new Promise<void>((resolve) => {
    finish = resolve;
  });
  const snapshot = {
    task: { id: 'saved', leadAgent: null },
    messages: [{ role: 'user' as const, seq: 1, text: 'restored turn', attachments: [] }],
    pendingAction: null,
  };
  mockApi = fakeTasksApi({
    read: jest
      .fn()
      .mockImplementationOnce(async () => {
        await waiting;
        return snapshot;
      })
      .mockResolvedValue(snapshot),
    close: jest.fn(async () => {
      throw new TaskBusyError('task_busy');
    }),
  });
  jest
    .spyOn(Alert, 'alert')
    .mockImplementation((_t, _m, buttons) =>
      buttons?.find((b) => b.style === 'destructive')?.onPress?.(),
    );
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask());
  await waitFor(() => expect(mockApi.read).toHaveBeenCalled());
  fireEvent.press(screen.getByTestId('task-restore-close'));
  await act(async () => finish());
  await screen.findByText('Still answering — try again in a second', {}, { timeout: 3000 });
  expect(useTaskSheet.getState().visible).toBe(true);
  expect(await SecureStore.getItemAsync('open_task_id')).toBe('saved');
  if (!screen.queryByText('restored turn')) fireEvent.press(screen.getByText('Retry'));
  expect(await screen.findByText('restored turn')).toBeTruthy();
  expect(screen.getByTestId('task-close')).toBeTruthy();
  expect(mockApi.open).not.toHaveBeenCalled();
  act(() => openTask({ send: 'continue' }));
  await waitFor(() =>
    expect(mockApi.post).toHaveBeenCalledWith('saved', { text: 'continue', attachments: [] }),
  );
});

import { TextInput } from 'react-native';
test.each(['voice', 'tap'] as const)(
  '%s opening derives focus before delayed task creation and streaming',
  async (intent) => {
    jest.useFakeTimers();
    const focus = jest.spyOn(TextInput.prototype, 'focus').mockClear();
    let create!: (task: { id: string; leadAgent: null }) => void;
    let finish!: () => void;
    const stream = new Promise<void>((resolve) => {
      finish = resolve;
    });
    mockApi = fakeTasksApi({
      open: jest.fn(
        () =>
          new Promise((resolve) => {
            create = resolve;
          }),
      ),
      post: jest.fn(() => ({
        events: (async function* () {
          await stream;
          yield { type: 'finished' as const };
        })(),
        abort: jest.fn(),
      })),
    });
    try {
      render(
        <ThemeProvider>
          <TaskSheet />
        </ThemeProvider>,
      );
      await act(async () =>
        openTask(intent === 'voice' ? { voice: { text: 'spoken', seconds: 2 } } : undefined),
      );
      await act(async () => jest.advanceTimersByTime(300));
      if (intent === 'voice') {
        expect(mockApi.open).toHaveBeenCalledTimes(1);
        expect(focus).not.toHaveBeenCalled();
        await act(async () => create({ id: 'delayed', leadAgent: null }));
        await act(async () => jest.advanceTimersByTime(300));
        expect(mockApi.post).toHaveBeenCalledTimes(1);
        expect(focus).not.toHaveBeenCalled();
        await act(async () => finish());
        await act(async () => jest.advanceTimersByTime(300));
        expect(focus).not.toHaveBeenCalled();
      } else expect(focus).toHaveBeenCalledTimes(1);
    } finally {
      focus.mockRestore();
      jest.useRealTimers();
    }
  },
);

import * as FileSystem from 'expo-file-system/legacy';
import * as Linking from 'expo-linking';
import { shareAttachment } from './share';
test('shared metadata failure keeps the request queued for retry before composer acceptance', async () => {
  jest.spyOn(Linking, 'parse').mockReturnValueOnce({
    queryParams: {
      shareFileURL: 'file:///shared.pdf',
      shareFileName: 'shared.pdf',
    },
  } as never);
  (FileSystem.getInfoAsync as jest.Mock)
    .mockResolvedValueOnce({ exists: false })
    .mockResolvedValueOnce({ exists: true, isDirectory: false, size: 10 });
  render(
    <ThemeProvider>
      <TaskSheet />
    </ThemeProvider>,
  );
  act(() => openTask({ attachments: [shareAttachment('lifeagents://share')!] }));
  expect(
    await screen.findByText('Could not check file size. Retry or choose the file again.'),
  ).toBeTruthy();
  expect(useTaskSheet.getState().pending?.attachments).toHaveLength(1);
  expect(screen.queryByText('shared.pdf')).toBeNull();
  fireEvent.press(screen.getByText('Retry'));
  expect(await screen.findByText('shared.pdf')).toBeTruthy();
  await waitFor(() => expect(useTaskSheet.getState().pending).toBeNull());
  expect(mockApi.post).not.toHaveBeenCalled();
});
test.each(['voice', 'hidden'] as const)(
  'tap focus is canceled when intent becomes %s before the timer',
  async (intent) => {
    jest.useFakeTimers();
    const focus = jest.spyOn(TextInput.prototype, 'focus').mockClear();
    try {
      render(
        <ThemeProvider>
          <TaskSheet />
        </ThemeProvider>,
      );
      await act(async () => openTask());
      await act(async () =>
        intent === 'voice'
          ? openTask({ voice: { text: 'spoken', seconds: 2 } })
          : useTaskSheet.getState().hide(),
      );
      await act(async () => jest.advanceTimersByTime(300));
      expect(focus).not.toHaveBeenCalled();
    } finally {
      focus.mockRestore();
      jest.useRealTimers();
    }
  },
);

// Reuses final-rereview-lifecycle-regression.test.tsx with explicit End confirmation.
test.each(['typed', 'palette'] as const)(
  '%s command tail stays behind the close barrier during delayed task creation',
  async (path) => {
    let resolveOpen!: (task: { id: string; leadAgent: 'nutrition' }) => void;
    mockApi = fakeTasksApi({
      open: jest.fn(
        () =>
          new Promise((resolve) => {
            resolveOpen = resolve;
          }),
      ),
    });
    const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
    render(
      <ThemeProvider>
        <TaskSheet />
      </ThemeProvider>,
    );
    await act(async () => openTask());
    await screen.findByTestId('task-close');
    fireEvent.changeText(screen.getByTestId('ask-input'), '/nutrition my meal');
    fireEvent.press(
      path === 'typed' ? screen.getByTestId('ask-send') : screen.getByText('/nutrition'),
    );
    await waitFor(() => expect(mockApi.open).toHaveBeenCalledWith('nutrition'));
    expect(mockApi.post).not.toHaveBeenCalled();
    fireEvent.press(screen.getByTestId('task-close'));
    expect(alert).toHaveBeenCalledWith('End task?', expect.any(String), expect.any(Array));
    expect(useTaskSheet.getState().visible).toBe(true);
    const end = alert.mock.calls[0]?.[2]?.find((button) => button.style === 'destructive');
    await act(async () => end?.onPress?.());
    await act(async () => resolveOpen({ id: 'late', leadAgent: 'nutrition' }));
    await waitFor(() => expect(mockApi.close).toHaveBeenCalledWith('late'));
    await waitFor(() => expect(useTaskSheet.getState().visible).toBe(false));
    expect(mockApi.post).not.toHaveBeenCalled();
    expect(await SecureStore.getItemAsync('open_task_id')).toBeNull();
  },
);
