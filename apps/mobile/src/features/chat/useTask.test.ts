import AsyncStorage from '@react-native-async-storage/async-storage';
import { AppState, type AppStateStatus } from 'react-native';
import { loadPendingDeletes, addPendingDelete } from './pendingDeletes';
import { act, renderHook, waitFor } from '@testing-library/react-native';
import * as SecureStore from 'expo-secure-store';
import type { TasksApi } from './tasksApi';
import { TaskBusyError } from './tasksApi';
import { useTask } from './useTask';

async function* gen(...items: object[]) {
  for (const i of items) yield i as never;
}

function fakeApi(overrides: Partial<TasksApi> = {}): jest.Mocked<TasksApi> {
  return {
    open: jest.fn(async (lead) => ({ id: 't1', leadAgent: lead ?? null })),
    read: jest.fn(async () => null),
    setLead: jest.fn(async (id, lead) => ({ id, leadAgent: lead })),
    close: jest.fn(async () => undefined),
    resolve: jest.fn(async () => ({ status: 'applied' as const, message: 'Готово.' })),
    post: jest.fn(() => ({
      events: gen(
        { type: 'routed', primary: 'sleep' },
        { type: 'text', delta: 'Спал ' },
        { type: 'text', delta: '7 ч.' },
        { type: 'consulted', peers: ['nutrition'] },
        { type: 'finished' },
      ),
      abort: jest.fn(),
    })),
    ...overrides,
  } as jest.Mocked<TasksApi>;
}

beforeEach(async () => {
  jest.spyOn(AppState, 'addEventListener').mockReturnValue({ remove: jest.fn() });
  await SecureStore.deleteItemAsync('open_task_id');
});

test('the first message opens a task lazily, stores its id and streams the reply', async () => {
  const api = fakeApi();
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'как я спал?' }));
  expect(api.open).toHaveBeenCalledWith(null);
  expect(api.post).toHaveBeenCalledWith('t1', { text: 'как я спал?', attachments: [] });
  expect(await SecureStore.getItemAsync('open_task_id')).toBe('t1');
  expect(result.current.messages.at(-1)).toMatchObject({
    kind: 'assistant',
    agent: 'sleep',
    consulted: ['nutrition'],
    text: 'Спал 7 ч.',
    streaming: false,
  });
  expect(result.current.phase).toBe('idle');
});

test('a tag before the first message opens the task with that lead; a later tag patches it', async () => {
  const api = fakeApi();
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ tag: 'nutrition', text: 'белок?' }));
  expect(api.open).toHaveBeenCalledWith('nutrition');
  await act(() => result.current.send({ tag: 'sleep', text: 'а сон?' }));
  expect(api.setLead).toHaveBeenCalledWith('t1', 'sleep');
  await act(() => result.current.setLead(null));
  expect(api.setLead).toHaveBeenLastCalledWith('t1', null);
  expect(result.current.leadAgent).toBeNull();
});

test('restore: found → transcript, lead and pending card; 404 → the id is cleared', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  const api = fakeApi({
    read: jest.fn(async () => ({
      task: { id: 't9', leadAgent: 'home' as const },
      messages: [
        { role: 'user' as const, seq: 1, text: 'выключи лампу', attachments: [] },
        {
          role: 'assistant' as const,
          seq: 2,
          text: 'Подтверди',
          agent: 'home' as const,
          consulted: [],
          action: {
            id: 'a1',
            summary: 'Выключить: Lamp?',
            status: 'pending' as const,
            expiresAt: '2026-10-14T18:05:00Z',
          },
        },
      ],
      pendingAction: {
        id: 'a1',
        summary: 'Выключить: Lamp?',
        status: 'pending' as const,
        expiresAt: '2026-10-14T18:05:00Z',
      },
    })),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.restore());
  expect(result.current.taskId).toBe('t9');
  expect(result.current.leadAgent).toBe('home');
  expect(result.current.pendingAction?.id).toBe('a1');
  expect(result.current.interrupted).toBe(false);

  const gone = fakeApi();
  const second = renderHook(() => useTask(gone));
  await act(() => second.result.current.restore());
  expect(second.result.current.taskId).toBeNull();
  expect(await SecureStore.getItemAsync('open_task_id')).toBeNull();
});

test('restore marks a transcript that ends with a user turn as interrupted', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  const api = fakeApi({
    read: jest.fn(async () => ({
      task: { id: 't9', leadAgent: null },
      messages: [{ role: 'user' as const, seq: 1, text: 'ну?', attachments: [] }],
      pendingAction: null,
    })),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.restore());
  expect(result.current.interrupted).toBe(true);
});

test('a proposal becomes a card; confirm resolves it once and updates the card', async () => {
  const api = fakeApi({
    post: jest.fn(() => ({
      events: gen(
        { type: 'routed', primary: 'home' },
        {
          type: 'proposed',
          action: {
            id: 'a1',
            summary: 'Выключить: Lamp?',
            expiresAt: '2026-10-14T18:05:00Z',
            status: 'pending',
          },
        },
        { type: 'text', delta: 'Подтверди' },
        { type: 'finished' },
      ),
      abort: jest.fn(),
    })),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'выключи лампу' }));
  expect(result.current.pendingAction?.id).toBe('a1');
  await act(async () => {
    await Promise.all([result.current.confirm('a1'), result.current.confirm('a1')]);
  });
  expect(api.resolve).toHaveBeenCalledTimes(1);
  expect(result.current.messages.at(-1)).toMatchObject({
    kind: 'assistant',
    action: { status: 'applied', message: 'Готово.' },
  });
  expect(result.current.pendingAction).toBeNull();
});

test('a typed "да" resolved by the server updates the card from ActionResolved', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  const card = {
    id: 'a1',
    summary: 'Выключить: Lamp?',
    status: 'pending' as const,
    expiresAt: '2026-10-14T18:05:00Z',
  };
  const api = fakeApi({
    read: jest.fn(async () => ({
      task: { id: 't9', leadAgent: 'home' as const },
      messages: [
        { role: 'user' as const, seq: 1, text: 'выключи лампу', attachments: [] },
        {
          role: 'assistant' as const,
          seq: 2,
          text: 'Подтверди',
          agent: 'home' as const,
          consulted: [],
          action: card,
        },
      ],
      pendingAction: card,
    })),
    post: jest.fn(() => ({
      events: gen(
        { type: 'routed', primary: 'home' },
        { type: 'resolved', actionId: 'a1', status: 'applied', message: 'Готово.' },
        { type: 'text', delta: 'Готово.' },
        { type: 'finished' },
      ),
      abort: jest.fn(),
    })),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.restore());
  await act(() => result.current.send({ text: 'да' }));
  expect(result.current.messages.find((m) => m.id === 's2')).toMatchObject({
    action: { status: 'applied', message: 'Готово.' },
  });
  expect(result.current.pendingAction).toBeNull();
  expect(api.resolve).not.toHaveBeenCalled();
});

test('RunError and HTTP errors become error bubbles; the streaming bubble is closed', async () => {
  const api = fakeApi({
    post: jest.fn(() => ({
      events: gen(
        { type: 'error', code: 'timeout', message: 'Слишком долго.' },
        { type: 'finished' },
      ),
      abort: jest.fn(),
    })),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'привет' }));
  expect(
    result.current.messages.some((m) => m.kind === 'error' && m.message === 'Слишком долго.'),
  ).toBe(true);
  expect(result.current.messages.some((m) => m.kind === 'assistant' && m.streaming)).toBe(false);
});

test('close aborts a running stream, retries task_busy and clears the id', async () => {
  const close = jest
    .fn()
    .mockRejectedValueOnce(new TaskBusyError('task_busy'))
    .mockResolvedValue(undefined);
  const api = fakeApi({ close });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'привет' }));
  await act(() => result.current.close());
  expect(close).toHaveBeenCalledTimes(2);
  expect(result.current.taskId).toBeNull();
  expect(result.current.messages).toEqual([]);
  expect(await SecureStore.getItemAsync('open_task_id')).toBeNull();
});

test('empty text is ignored and a second send cannot overlap an in-flight send', async () => {
  let release!: () => void;
  const api = fakeApi({
    open: jest.fn(async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return { id: 't1', leadAgent: null };
    }),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: '  ' }));
  expect(api.open).not.toHaveBeenCalled();
  let sending!: Promise<unknown>;
  act(() => {
    sending = result.current.send({ text: 'first' });
  });
  await act(() => result.current.send({ text: 'second' }));
  await act(async () => {
    release();
    await sending;
  });
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(result.current.messages.filter((m) => m.kind === 'user')).toHaveLength(1);
});

test('close preserves the task after three busy responses', async () => {
  jest.useFakeTimers();
  try {
    const api = fakeApi({ close: jest.fn().mockRejectedValue(new TaskBusyError('task_busy')) });
    const { result } = renderHook(() => useTask(api));
    await act(() => result.current.send({ text: 'hello' }));
    const closed = result.current.close().catch((error: unknown) => error);
    await act(async () => {
      await jest.advanceTimersByTimeAsync(1000);
    });
    expect(await closed).toBeInstanceOf(TaskBusyError);
    expect(api.close).toHaveBeenCalledTimes(3);
    expect(result.current.taskId).toBe('t1');
    expect(await SecureStore.getItemAsync('open_task_id')).toBe('t1');
  } finally {
    jest.useRealTimers();
  }
});

test('restore blocks sending until the saved transcript has been loaded', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  let release!: () => void;
  const api = fakeApi({
    read: jest.fn(async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return { task: { id: 't9', leadAgent: null }, messages: [], pendingAction: null };
    }),
  });
  const { result } = renderHook(() => useTask(api));
  let restoring!: Promise<void>;
  act(() => {
    restoring = result.current.restore();
  });
  await waitFor(() => expect(api.read).toHaveBeenCalled());
  await act(() => result.current.send({ text: 'hello' }));
  await act(async () => {
    release();
    await restoring;
  });
  expect(api.open).not.toHaveBeenCalled();
  expect(api.post).not.toHaveBeenCalled();
  expect(result.current.taskId).toBe('t9');
});

test('structured API errors keep their code for localization', async () => {
  const { TasksApiError } = await import('./tasksApi');
  const api = fakeApi({
    open: jest.fn().mockRejectedValue(new TasksApiError('no_household', 422)),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ tag: 'home', text: 'hello' }));
  expect(result.current.messages.at(-1)).toMatchObject({ kind: 'error', code: 'no_household' });
});

test('close waits for task creation and never posts after close was requested', async () => {
  let release!: () => void;
  const api = fakeApi({
    open: jest.fn(async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return { id: 't1', leadAgent: null };
    }),
  });
  const { result } = renderHook(() => useTask(api));
  let sending!: Promise<unknown>;
  act(() => {
    sending = result.current.send({ text: 'hello' });
  });
  await waitFor(() => expect(api.open).toHaveBeenCalled());
  let closing!: Promise<void>;
  await act(async () => {
    closing = result.current.close();
    release();
    await Promise.all([sending, closing]);
  });
  expect(api.close).toHaveBeenCalledWith('t1');
  expect(api.post).not.toHaveBeenCalled();
  expect(result.current.taskId).toBeNull();
  expect(await SecureStore.getItemAsync('open_task_id')).toBeNull();
});

test('close aborts an active stream before deleting the task', async () => {
  let stop!: () => void;
  const abort = jest.fn(() => stop());
  const api = fakeApi({
    post: jest.fn(() => ({
      abort,
      events: (async function* () {
        yield { type: 'text' as const, delta: 'partial' };
        await new Promise<void>((resolve) => {
          stop = resolve;
        });
      })(),
    })),
  });
  const { result } = renderHook(() => useTask(api));
  let sending!: Promise<unknown>;
  act(() => {
    sending = result.current.send({ text: 'hello' });
  });
  await waitFor(() => expect(result.current.phase).toBe('streaming'));
  await act(async () => {
    await result.current.close();
    await sending;
  });
  expect(abort).toHaveBeenCalledTimes(1);
  expect(api.close).toHaveBeenCalledWith('t1');
  expect(result.current.messages).toEqual([]);
});

test('close waits for restoration and deletes the restored task', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  let release!: () => void;
  const api = fakeApi({
    read: jest.fn(async () => {
      await new Promise<void>((resolve) => {
        release = resolve;
      });
      return { task: { id: 't9', leadAgent: null }, messages: [], pendingAction: null };
    }),
  });
  const { result } = renderHook(() => useTask(api));
  let restoring!: Promise<void>;
  act(() => {
    restoring = result.current.restore();
  });
  await waitFor(() => expect(api.read).toHaveBeenCalled());
  await act(async () => {
    const closing = result.current.close();
    release();
    await Promise.all([restoring, closing]);
  });
  expect(api.close).toHaveBeenCalledWith('t9');
  expect(result.current.taskId).toBeNull();
});

test('failed restoration cannot overwrite the stored task on the next send', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  const api = fakeApi({ read: jest.fn().mockRejectedValue(new Error('network')) });
  const { result } = renderHook(() => useTask(api));
  await act(async () => {
    await result.current.restore().catch(() => undefined);
  });
  await act(() => result.current.send({ text: 'hello' }));
  expect(api.open).not.toHaveBeenCalled();
  expect(await SecureStore.getItemAsync('open_task_id')).toBe('t9');
});

test('retrying restoration keeps the old transcript and displays the newly sent reply', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  const api = fakeApi({
    read: jest
      .fn()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValue({
        task: { id: 't9', leadAgent: null },
        messages: [{ role: 'user', seq: 1, text: 'old', attachments: [] }],
        pendingAction: null,
      }),
  });
  const { result } = renderHook(() => useTask(api));
  await act(async () => {
    await result.current.restore().catch(() => undefined);
  });
  await act(() => result.current.send({ text: 'new' }));
  expect(api.open).not.toHaveBeenCalled();
  expect(result.current.messages.filter((m) => m.kind === 'user').map((m) => m.text)).toEqual([
    'old',
    'new',
  ]);
  expect(result.current.messages.at(-1)).toMatchObject({ kind: 'assistant', text: 'Спал 7 ч.' });
});

test('a replacement proposal expires the previous pending card', async () => {
  let n = 0;
  const api = fakeApi({
    post: jest.fn(() => ({
      abort: jest.fn(),
      events: gen(
        {
          type: 'proposed',
          action: { id: `a${++n}`, summary: 'Confirm', status: 'pending', expiresAt: null },
        },
        { type: 'finished' },
      ),
    })),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'first' }));
  await act(() => result.current.send({ text: 'second' }));
  expect(
    result.current.messages.find((m) => m.kind === 'assistant' && m.action?.id === 'a1'),
  ).toMatchObject({ action: { status: 'expired' } });
  expect(result.current.pendingAction?.id).toBe('a2');
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

test('close waits for an unread-task retry and invalidates the waiting send', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  const read = deferred<Awaited<ReturnType<TasksApi['read']>>>();
  const api = fakeApi({
    read: jest.fn().mockRejectedValueOnce(new Error('network')).mockReturnValueOnce(read.promise),
  });
  const { result } = renderHook(() => useTask(api));
  await act(async () => {
    await result.current.restore().catch(() => undefined);
  });
  let send!: Promise<unknown>;
  act(() => {
    send = result.current.send({ text: 'new' });
  });
  await waitFor(() => expect(api.read).toHaveBeenCalledTimes(2));
  await act(async () => {
    const close = result.current.close();
    read.resolve({ task: { id: 't9', leadAgent: null }, messages: [], pendingAction: null });
    await Promise.all([send, close]);
  });
  expect(api.post).not.toHaveBeenCalled();
  expect(api.close).toHaveBeenCalledWith('t9');
  expect(result.current.taskId).toBeNull();
  expect(result.current.messages).toEqual([]);
  expect(await SecureStore.getItemAsync('open_task_id')).toBeNull();
});

test('close waits for a lead patch and invalidates the waiting send', async () => {
  const patch = deferred<Awaited<ReturnType<TasksApi['setLead']>>>();
  const api = fakeApi({ setLead: jest.fn(() => patch.promise) });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'first' }));
  api.post.mockClear();
  let send!: Promise<unknown>;
  act(() => {
    send = result.current.send({ tag: 'sleep', text: 'next' });
  });
  await waitFor(() => expect(api.setLead).toHaveBeenCalled());
  await act(async () => {
    const close = result.current.close();
    patch.resolve({ id: 't1', leadAgent: 'sleep' });
    await Promise.all([send, close]);
  });
  expect(api.post).not.toHaveBeenCalled();
  expect(result.current.taskId).toBeNull();
  expect(result.current.leadAgent).toBeNull();
});

test('rapid lead changes are applied in order including clearing an in-flight lead', async () => {
  const patch = deferred<Awaited<ReturnType<TasksApi['setLead']>>>();
  const api = fakeApi({
    setLead: jest
      .fn()
      .mockReturnValueOnce(patch.promise)
      .mockResolvedValueOnce({ id: 't1', leadAgent: null }),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'first' }));
  let first!: Promise<void>;
  let second!: Promise<void>;
  act(() => {
    first = result.current.setLead('sleep');
    second = result.current.setLead(null);
  });
  await waitFor(() => expect(api.setLead).toHaveBeenCalledWith('t1', 'sleep'));
  await act(async () => {
    patch.resolve({ id: 't1', leadAgent: 'sleep' });
    await Promise.all([first, second]);
  });
  expect(api.setLead).toHaveBeenLastCalledWith('t1', null);
  expect(result.current.leadAgent).toBeNull();
});

test('send reports initialization failure to allow the composer to retain its input', async () => {
  const api = fakeApi({ open: jest.fn().mockRejectedValue(new Error('network')) });
  const { result } = renderHook(() => useTask(api));
  let accepted: unknown;
  await act(async () => {
    accepted = await result.current.send({
      text: 'keep me',
      attachments: [
        { uri: 'file://report', name: 'report.pdf', mime: 'application/pdf', size: 10 },
      ],
    });
  });
  expect(accepted).toBe(false);
  expect(api.post).not.toHaveBeenCalled();
});

test('lost action response keeps the pending card retryable until a server result arrives', async () => {
  const api = fakeApi({
    post: jest.fn(() => ({
      abort: jest.fn(),
      events: gen(
        {
          type: 'proposed',
          action: { id: 'a1', summary: 'Confirm', status: 'pending', expiresAt: null },
        },
        { type: 'finished' },
      ),
    })),
    resolve: jest
      .fn()
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ status: 'applied', message: 'Done' }),
  });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'first' }));
  await act(() => result.current.confirm('a1'));
  expect(result.current.pendingAction?.status).toBe('pending');
  expect(result.current.messages.find((m) => m.kind === 'assistant')).toMatchObject({
    action: { status: 'pending' },
  });
  await act(() => result.current.confirm('a1'));
  expect(result.current.pendingAction).toBeNull();
  expect(result.current.messages.find((m) => m.kind === 'assistant')).toMatchObject({
    action: { status: 'applied' },
  });
});

test('a failed lead patch reports unsent input without posting', async () => {
  const api = fakeApi({ setLead: jest.fn().mockRejectedValue(new Error('network')) });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'first' }));
  api.post.mockClear();
  let sent: unknown;
  await act(async () => {
    sent = await result.current.send({
      text: 'retain this',
      tag: 'sleep',
      attachments: [
        { uri: 'file://report', name: 'report.pdf', mime: 'application/pdf', size: 10 },
      ],
    });
  });
  expect(sent).toBe(false);
  expect(api.post).not.toHaveBeenCalled();
  expect(result.current.taskId).toBe('t1');
});

test('failed restore retry reports unsent input and retains the saved task', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  const api = fakeApi({ read: jest.fn().mockRejectedValue(new Error('network')) });
  const { result } = renderHook(() => useTask(api));
  await act(async () => {
    await result.current.restore().catch(() => undefined);
  });
  let sent: unknown;
  await act(async () => {
    sent = await result.current.send({ text: 'retain this' });
  });
  expect(sent).toBe(false);
  expect(api.post).not.toHaveBeenCalled();
  expect(await SecureStore.getItemAsync('open_task_id')).toBe('t9');
});

test('offline close persists delete before forgetting identity and restore retries it', async () => {
  const api = fakeApi({ close: jest.fn().mockRejectedValue(new TypeError('offline')) });
  const first = renderHook(() => useTask(api));
  await act(() => first.result.current.send({ text: 'hello' }));
  await act(() => first.result.current.close());
  expect(first.result.current.taskId).toBeNull();
  expect(await SecureStore.getItemAsync('open_task_id')).toBeNull();
  expect(await loadPendingDeletes()).toEqual(['t1']);
  first.unmount();
  const online = fakeApi();
  const second = renderHook(() => useTask(online));
  await act(() => second.result.current.restore());
  expect(online.close).toHaveBeenCalledWith('t1');
  expect(online.read).not.toHaveBeenCalled();
  expect(await loadPendingDeletes()).toEqual([]);
});

test('failed queue persistence retains the saved identity and visible task', async () => {
  const api = fakeApi({ close: jest.fn().mockRejectedValue(new TypeError('offline')) });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.send({ text: 'hello' }));
  jest.spyOn(AsyncStorage, 'setItem').mockRejectedValueOnce(new Error('disk full'));
  await act(async () => {
    await expect(result.current.close()).rejects.toThrow('disk full');
  });
  expect(result.current.taskId).toBe('t1');
  expect(await SecureStore.getItemAsync('open_task_id')).toBe('t1');
});

test('restore never reads a queued offline task', async () => {
  await SecureStore.setItemAsync('open_task_id', 't9');
  await addPendingDelete('t9');
  const api = fakeApi({ close: jest.fn().mockRejectedValue(new TypeError('offline')) });
  const { result } = renderHook(() => useTask(api));
  await act(() => result.current.restore());
  expect(api.read).not.toHaveBeenCalled();
  expect(result.current.taskId).toBeNull();
  expect(await loadPendingDeletes()).toEqual(['t9']);
});

test('app resume retries pending deletes and removes its listener on unmount', async () => {
  let resume!: (state: AppStateStatus) => void;
  const remove = jest.fn();
  const listener = jest
    .spyOn(AppState, 'addEventListener')
    .mockImplementation((_event, callback) => {
      resume = callback;
      return { remove };
    });
  await addPendingDelete('old');
  const api = fakeApi();
  const hook = renderHook(() => useTask(api));
  await act(async () => {
    resume('active');
  });
  expect(api.close).toHaveBeenCalledWith('old');
  expect(await loadPendingDeletes()).toEqual([]);
  hook.unmount();
  expect(remove).toHaveBeenCalled();
  listener.mockRestore();
});

test('queued deletes retry with backoff only in foreground and stop after success', async () => {
  jest.useFakeTimers();
  let change!: (state: AppStateStatus) => void;
  const listener = jest
    .spyOn(AppState, 'addEventListener')
    .mockImplementation((_event, callback) => {
      change = callback;
      return { remove: jest.fn() };
    });
  try {
    const api = fakeApi({ close: jest.fn().mockRejectedValueOnce(new TypeError('offline')) });
    const hook = renderHook(() => useTask(api));
    await act(() => hook.result.current.send({ text: 'hello' }));
    await act(() => hook.result.current.close());
    await act(async () => {
      change('background');
      await jest.advanceTimersByTimeAsync(60000);
    });
    expect(api.close).toHaveBeenCalledTimes(1);
    api.close.mockRejectedValueOnce(new TypeError('offline'));
    await act(async () => {
      change('active');
    });
    expect(api.close).toHaveBeenCalledTimes(2);
    await act(async () => {
      await jest.advanceTimersByTimeAsync(10000);
    });
    expect(api.close).toHaveBeenCalledTimes(3);
    expect(await loadPendingDeletes()).toEqual([]);
    await act(async () => {
      await jest.advanceTimersByTimeAsync(120000);
    });
    expect(api.close).toHaveBeenCalledTimes(3);
    hook.unmount();
    expect(jest.getTimerCount()).toBe(0);
  } finally {
    listener.mockRestore();
    jest.useRealTimers();
  }
});

test('a queue read failure during restore retains the saved-task barrier on send', async () => {
  await SecureStore.setItemAsync('open_task_id', 'saved');
  const api = fakeApi({ read: jest.fn().mockRejectedValue(new TypeError('offline')) });
  const { result } = renderHook(() => useTask(api));
  // The mount scheduler reads storage too; let its initial check complete first.
  await act(async () => {
    await Promise.resolve();
  });
  jest.spyOn(AsyncStorage, 'getItem').mockRejectedValueOnce(new Error('disk'));
  await act(async () => {
    await result.current.restore().catch(() => undefined);
  });
  await act(() => result.current.send({ text: 'keep identity' }));
  expect(api.open).not.toHaveBeenCalled();
  expect(await SecureStore.getItemAsync('open_task_id')).toBe('saved');
});
