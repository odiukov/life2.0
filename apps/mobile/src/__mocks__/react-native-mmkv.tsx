const store = new Map<string, string>();
export function createMMKV() {
  return {
    getString: (k: string) => store.get(k) ?? null,
    set: (k: string, v: string) => store.set(k, v),
    remove: (k: string) => store.delete(k),
  };
}
export class MMKV {
  getString(k: string) { return store.get(k) ?? null; }
  set(k: string, v: string) { store.set(k, v); }
  remove(k: string) { store.delete(k); }
  delete(k: string) { store.delete(k); }
}
