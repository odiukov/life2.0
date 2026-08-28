import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';

type SyncTimestampState = {
  lastSyncedAt: number | null; // unix ms
  isSyncing: boolean;
  setSyncing: (b: boolean) => void;
  /**
   * Ends the current sync attempt (success or failure) and records the
   * wall-clock time. Also flips isSyncing back to false. Call from a
   * finally block, not only on success.
   */
  markSynced: () => void;
};

export const useSyncTimestamp = create<SyncTimestampState>()(
  persist(
    (set) => ({
      lastSyncedAt: null,
      isSyncing: false,
      setSyncing: (b) => set({ isSyncing: b }),
      markSynced: () => set({ lastSyncedAt: Date.now(), isSyncing: false }),
    }),
    {
      name: 'sync-timestamp',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (s) => ({ lastSyncedAt: s.lastSyncedAt }), // never persist isSyncing
    },
  ),
);
