import AsyncStorage from '@react-native-async-storage/async-storage';
import { TasksApiError } from './tasksApi';
import { addPendingDelete, flushPendingDeletes, loadPendingDeletes } from './pendingDeletes';

beforeEach(async () => AsyncStorage.clear());

test('ids are stored once and flushed; 404 counts as done, other errors stay queued', async () => {
  await addPendingDelete('a');
  await addPendingDelete('a');
  await addPendingDelete('b');
  await addPendingDelete('c');
  const close = jest.fn(async (id: string) => {
    if (id === 'b') throw new TasksApiError('task_not_found', 404);
    if (id === 'c') throw new TypeError('Network request failed');
  });
  await flushPendingDeletes(close);
  expect(close.mock.calls.map((c) => c[0])).toEqual(['a', 'b', 'c']);
  expect(await loadPendingDeletes()).toEqual(['c']);
});

test('garbage in storage reads as empty', async () => {
  await AsyncStorage.setItem('pending_task_deletes', '{"not":"a list"}');
  expect(await loadPendingDeletes()).toEqual([]);
});

test('concurrent queue changes preserve every id and removals', async () => {
  await Promise.all([addPendingDelete('a'), addPendingDelete('b'), addPendingDelete('c')]);
  expect(await loadPendingDeletes()).toEqual(['a', 'b', 'c']);
});

test('a queue write failure rejects instead of claiming durability', async () => {
  jest.spyOn(AsyncStorage, 'setItem').mockRejectedValueOnce(new Error('disk full'));
  await expect(addPendingDelete('a')).rejects.toThrow('disk full');
  expect(await loadPendingDeletes()).toEqual([]);
});

test('a delete added during a flush survives completion of the old request', async () => {
  await addPendingDelete('old');
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  const close = jest.fn(() => blocked);
  const flush = flushPendingDeletes(close);
  while (!close.mock.calls.length) await Promise.resolve();
  await addPendingDelete('new');
  release();
  await flush;
  expect(await loadPendingDeletes()).toEqual(['new']);
});

test('overlapping flushes delete each snapshot id once', async () => {
  await addPendingDelete('old');
  const close = jest.fn(async () => undefined);
  await Promise.all([flushPendingDeletes(close), flushPendingDeletes(close)]);
  expect(close).toHaveBeenCalledTimes(1);
  expect(await loadPendingDeletes()).toEqual([]);
});

test('storage read failures cannot silently replace a durable queue', async () => {
  await addPendingDelete('old');
  jest.spyOn(AsyncStorage, 'getItem').mockRejectedValueOnce(new Error('disk'));
  await expect(addPendingDelete('new')).rejects.toThrow('disk');
  expect(await loadPendingDeletes()).toEqual(['old']);
});
