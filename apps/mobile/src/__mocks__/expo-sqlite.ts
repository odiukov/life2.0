/**
 * Jest mock for expo-sqlite.
 *
 * Backed by better-sqlite3 (sync) with an async-shaped surface matching the
 * subset of expo-sqlite we actually call: openDatabaseAsync, execAsync,
 * runAsync, getFirstAsync, getAllAsync, closeAsync.
 *
 * Note: better-sqlite3 has no real "named in-memory" feature — any name that
 * starts with ':memory:' becomes a fresh isolated DB. That's fine for tests;
 * each openDatabaseAsync(':memory:...') call returns a new handle.
 */
import Database from 'better-sqlite3';

type Params = readonly unknown[] | undefined;

function wrap(db: Database.Database) {
  return {
    execAsync: (sql: string) =>
      new Promise<void>((resolve, reject) => {
        try {
          db.exec(sql);
          resolve();
        } catch (e) {
          reject(e);
        }
      }),
    runAsync: (sql: string, params?: Params) =>
      new Promise((resolve, reject) => {
        try {
          const result = db.prepare(sql).run(...((params ?? []) as unknown[]));
          resolve(result);
        } catch (e) {
          reject(e);
        }
      }),
    getFirstAsync: <T = unknown>(sql: string, params?: Params) =>
      new Promise<T | undefined>((resolve, reject) => {
        try {
          const row = db.prepare(sql).get(...((params ?? []) as unknown[]));
          resolve(row as T | undefined);
        } catch (e) {
          reject(e);
        }
      }),
    getAllAsync: <T = unknown>(sql: string, params?: Params) =>
      new Promise<T[]>((resolve, reject) => {
        try {
          const rows = db.prepare(sql).all(...((params ?? []) as unknown[]));
          resolve(rows as T[]);
        } catch (e) {
          reject(e);
        }
      }),
    closeAsync: () =>
      new Promise<void>((resolve, reject) => {
        try {
          db.close();
          resolve();
        } catch (e) {
          reject(e);
        }
      }),
  };
}

export function openDatabaseAsync(name: string) {
  // expo-sqlite uses ':memory:' literally. Tests may pass ':memory:?u=X' for
  // naming clarity; strip the suffix so better-sqlite3 gets a valid token.
  const cleaned =
    name === ':memory:' || name.startsWith(':memory:') ? ':memory:' : name;
  return Promise.resolve(wrap(new Database(cleaned)));
}

export type SQLiteDatabase = ReturnType<typeof wrap>;
