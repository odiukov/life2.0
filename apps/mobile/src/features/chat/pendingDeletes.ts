import AsyncStorage from '@react-native-async-storage/async-storage';
import { TasksApiError } from './tasksApi';

const KEY = 'pending_task_deletes';
let mutations: Promise<void> = Promise.resolve();
const listeners = new Set<() => void>();

export function subscribePendingDeletes(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

let flushing: Promise<void> | null = null;

function serialize<T>(operation: () => Promise<T>): Promise<T> {
  const result = mutations.then(operation);
  mutations = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

async function read(): Promise<string[]> {
  const raw = await AsyncStorage.getItem(KEY);
  let value: unknown;
  try {
    value = raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
  return Array.isArray(value)
    ? [...new Set(value.filter((x): x is string => typeof x === 'string'))]
    : [];
}

/** Storage errors propagate: callers must not forget an identity without a durable queue. */
export function loadPendingDeletes(): Promise<string[]> {
  return serialize(read);
}
export function addPendingDelete(id: string): Promise<void> {
  return serialize(async () => {
    const ids = await read();
    if (!ids.includes(id)) {
      await AsyncStorage.setItem(KEY, JSON.stringify([...ids, id]));
      listeners.forEach((listener) => listener());
    }
  });
}
export function removePendingDelete(id: string): Promise<void> {
  return serialize(async () => {
    await AsyncStorage.setItem(KEY, JSON.stringify((await read()).filter((x) => x !== id)));
  });
}

/** Single-flight network retries do not hold the storage lock across HTTP calls. */
export function flushPendingDeletes(
  close: (id: string) => Promise<void>,
  shouldContinue: () => boolean = () => true,
): Promise<void> {
  if (flushing) return flushing;
  flushing = (async () => {
    for (const id of await loadPendingDeletes()) {
      if (!shouldContinue()) break;
      try {
        await close(id);
      } catch (error) {
        if (!(error instanceof TasksApiError && error.status === 404)) continue;
      }
      await removePendingDelete(id);
    }
  })().finally(() => {
    flushing = null;
  });
  return flushing;
}
