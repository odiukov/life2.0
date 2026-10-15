import { gateway } from '@/api/gateway';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';
import { postSse } from './sse';
import { realTasksApi, TaskBusyError, TasksApiError } from './tasksApi';

jest.mock('@/api/client', () => ({ apiBaseUrl: 'https://example.test', apiMode: 'local' }));
jest.mock('@/api/gateway', () => ({
  gateway: { GET: jest.fn(), POST: jest.fn(), PATCH: jest.fn(), DELETE: jest.fn() },
  errorCode: (error: { detail?: string } | undefined) => error?.detail,
}));
jest.mock('@/features/auth/getAuthHeaders', () => ({ getAuthHeaders: jest.fn() }));
jest.mock('./sse', () => ({ postSse: jest.fn() }));
jest.mock('./mockTasksApi', () => ({ mockTasksApi: {} }));
const api = gateway as unknown as Record<'GET' | 'POST' | 'PATCH' | 'DELETE', jest.Mock>;
const auth = getAuthHeaders as jest.Mock;
const streamPost = postSse as jest.Mock;
beforeEach(() => {
  jest.clearAllMocks();
});

test('opens with an optional lead and clears the lead with explicit null', async () => {
  api.POST.mockResolvedValue({ data: { id: 't1', lead_agent: 'sleep' } });
  expect(await realTasksApi.open('sleep')).toEqual({ id: 't1', leadAgent: 'sleep' });
  expect(api.POST).toHaveBeenCalledWith('/tasks', { body: { lead_agent: 'sleep' } });
  api.PATCH.mockResolvedValue({ data: { id: 't1', lead_agent: null } });
  expect(await realTasksApi.setLead('t1', null)).toEqual({ id: 't1', leadAgent: null });
  expect(api.PATCH).toHaveBeenCalledWith('/tasks/{task_id}', {
    params: { path: { task_id: 't1' } },
    body: { lead_agent: null },
  });
});

test('maps transcript attachments, known agents and matching pending action expiry', async () => {
  const attachments = [{ kind: 'document', name: 'meal.pdf', mime: 'application/pdf', size: 20 }];
  api.GET.mockResolvedValue({
    data: {
      task: { id: 't1', lead_agent: 'main' },
      pending_action: { id: 'a1', summary: 'Switch off?', expires_at: '2026-10-14T18:05:00Z' },
      messages: [
        { seq: 1, role: 'user', text: 'hi', attachments },
        {
          seq: 2,
          role: 'assistant',
          text: 'Confirm',
          agent: 'home',
          consulted: ['sleep', 'astrology'],
          action: { id: 'a1', summary: 'Switch off?', status: 'pending' },
        },
      ],
    },
  });
  const result = await realTasksApi.read('t1');
  expect(result?.task).toEqual({ id: 't1', leadAgent: null });
  expect(result?.messages[0]).toEqual({ seq: 1, role: 'user', text: 'hi', attachments });
  expect(result?.messages[1]).toMatchObject({
    consulted: ['sleep'],
    action: { id: 'a1', expiresAt: '2026-10-14T18:05:00Z' },
  });
  expect(result?.pendingAction).toEqual({
    id: 'a1',
    summary: 'Switch off?',
    expiresAt: '2026-10-14T18:05:00Z',
    status: 'pending',
  });
});

test('404 means missing on read and already closed on delete', async () => {
  const missing = { response: { status: 404 }, error: { detail: 'not_found' } };
  api.GET.mockResolvedValue(missing);
  api.DELETE.mockResolvedValue(missing);
  expect(await realTasksApi.read('t1')).toBeNull();
  await expect(realTasksApi.close('t1')).resolves.toBeUndefined();
});

test('propagates task busy and other structured errors', async () => {
  api.DELETE.mockResolvedValue({ response: { status: 409 }, error: { detail: 'task_busy' } });
  await expect(realTasksApi.close('t1')).rejects.toBeInstanceOf(TaskBusyError);
  api.POST.mockResolvedValue({ response: { status: 422 }, error: { detail: 'unknown_agent' } });
  await expect(realTasksApi.open()).rejects.toEqual(new TasksApiError('unknown_agent', 422));
});

test('resolves an action using both identifiers and the explicit decision', async () => {
  api.POST.mockResolvedValue({ data: { status: 'applied', message: 'Done' } });
  expect(await realTasksApi.resolve('t1', 'a1', 'confirm')).toEqual({
    status: 'applied',
    message: 'Done',
  });
  expect(api.POST).toHaveBeenCalledWith('/tasks/{task_id}/actions/{action_id}', {
    params: { path: { task_id: 't1', action_id: 'a1' } },
    body: { decision: 'confirm' },
  });
});

test('posts authenticated multipart text, timezone and attachments to the encoded task URL', async () => {
  auth.mockResolvedValue({ Authorization: 'Bearer token' });
  const abort = jest.fn();
  async function* events() {
    yield { type: 'finished' as const };
  }
  streamPost.mockReturnValue({ events: events(), abort });
  const append = jest.spyOn(FormData.prototype, 'append');
  const stream = realTasksApi.post('task/id', {
    text: 'hello',
    attachments: [{ uri: 'file:///meal.pdf', name: 'meal.pdf', mime: 'application/pdf', size: 20 }],
  });
  expect(await stream.events.next()).toEqual({ done: false, value: { type: 'finished' } });
  expect(streamPost).toHaveBeenCalledWith(
    'https://example.test/tasks/task%2Fid/messages',
    { Authorization: 'Bearer token' },
    expect.any(FormData),
  );
  expect(append).toHaveBeenCalledWith('text', 'hello');
  expect(append).toHaveBeenCalledWith('timezone', expect.any(String));
  expect(append).toHaveBeenCalledWith('attachments', {
    uri: 'file:///meal.pdf',
    name: 'meal.pdf',
    type: 'application/pdf',
  });
  stream.abort();
  expect(abort).toHaveBeenCalledTimes(1);
  append.mockRestore();
});

test('abort while authentication is pending prevents opening the transport', async () => {
  let resolve!: (headers: Record<string, string>) => void;
  auth.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const stream = realTasksApi.post('t1', { text: 'hello' });
  const next = stream.events.next();
  stream.abort();
  resolve({ Authorization: 'Bearer token' });
  expect(await next).toEqual({ done: true, value: undefined });
  expect(streamPost).not.toHaveBeenCalled();
});
