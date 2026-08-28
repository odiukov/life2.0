// In-memory AsyncStorage mock for Jest. Mirrors the subset zustand/persist uses.
const store = new Map<string, string>();

// Auto-isolate state across tests in the same file.
if (typeof beforeEach === 'function') {
  beforeEach(() => store.clear());
}

const AsyncStorage = {
  setItem: jest.fn(async (key: string, value: string) => {
    store.set(key, value);
  }),
  getItem: jest.fn(async (key: string) => store.get(key) ?? null),
  removeItem: jest.fn(async (key: string) => {
    store.delete(key);
  }),
  clear: jest.fn(async () => {
    store.clear();
  }),
  getAllKeys: jest.fn(async () => Array.from(store.keys())),
  multiGet: jest.fn(async (keys: string[]) =>
    keys.map((k) => [k, store.get(k) ?? null] as [string, string | null]),
  ),
  multiSet: jest.fn(async (pairs: Array<[string, string]>) => {
    pairs.forEach(([k, v]) => store.set(k, v));
  }),
  multiRemove: jest.fn(async (keys: string[]) => {
    keys.forEach((k) => store.delete(k));
  }),
};

export default AsyncStorage;
