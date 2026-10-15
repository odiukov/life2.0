import type { TasksApi } from './tasksApi';
export async function* gen(...items: object[]) {
  for (const i of items) yield i as never;
}

export function fakeTasksApi(overrides: Partial<TasksApi> = {}): jest.Mocked<TasksApi> {
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
