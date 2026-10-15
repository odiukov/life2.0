import { mockTasksApi } from './mockTasksApi';

test('stores task transcript and resolves the proposed action', async () => {
  const task = await mockTasksApi.open('home');
  const events = [];
  for await (const event of mockTasksApi.post(task.id, { text: 'turn off the light' }).events)
    events.push(event);
  expect(events.some((e) => e.type === 'proposed')).toBe(true);
  const snapshot = await mockTasksApi.read(task.id);
  expect(snapshot?.messages).toHaveLength(2);
  const action = snapshot!.pendingAction!;
  expect((await mockTasksApi.resolve(task.id, action.id, 'confirm')).status).toBe('applied');
  expect((await mockTasksApi.read(task.id))?.pendingAction).toBeNull();
  await mockTasksApi.close(task.id);
  expect(await mockTasksApi.read(task.id)).toBeNull();
});
