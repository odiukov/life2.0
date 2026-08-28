import { create } from 'zustand';
import * as SecureStore from 'expo-secure-store';
import { useEffect } from 'react';

export type IntegrationId =
  | 'apple-health'
  | 'garmin'
  | 'strava'
  | 'calendar'
  | 'ha'
  | 'payoneer'
  | 'yazio';

export type IntegrationStatus = 'connected' | 'not-connected' | 'manual-upload' | 'device-only';

// Source-of-truth: each panel stores a per-integration flag in expo-secure-store
// when the user connects. Presence of the key = connected. Strava and payoneer
// have no panel yet, so no key (null).
export const INTEGRATION_SECURE_KEYS: Record<IntegrationId, string | null> = {
  'apple-health': 'hk_last_sync',
  garmin: 'garmin_connected',
  yazio: 'yazio_connected',
  calendar: 'gcal_connected',
  ha: 'ha_connected',
  strava: null,
  payoneer: null,
};

type IntegrationsState = {
  status: Record<IntegrationId, IntegrationStatus>;
  toggle: (id: IntegrationId) => void;
  set: (id: IntegrationId, status: IntegrationStatus) => void;
};

const initialStatus: Record<IntegrationId, IntegrationStatus> = {
  'apple-health': 'not-connected',
  garmin: 'not-connected',
  strava: 'not-connected',
  calendar: 'not-connected',
  ha: 'not-connected',
  payoneer: 'manual-upload',
  yazio: 'device-only',
};

// For gating commands we treat any of these as "connected enough"
export function isConnected(status: IntegrationStatus): boolean {
  return status === 'connected' || status === 'manual-upload';
}

export const useIntegrationsStore = create<IntegrationsState>((set) => ({
  status: initialStatus,
  toggle: (id) =>
    set((s) => {
      const current = s.status[id];
      const next: IntegrationStatus = current === 'not-connected' ? 'connected' : 'not-connected';
      return { status: { ...s.status, [id]: next } };
    }),
  set: (id, status) => set((s) => ({ status: { ...s.status, [id]: status } })),
}));

export function useConnectedIntegrations(): Set<IntegrationId> {
  const status = useIntegrationsStore((s) => s.status);
  const connected = new Set<IntegrationId>();
  for (const [id, st] of Object.entries(status) as [IntegrationId, IntegrationStatus][]) {
    if (isConnected(st)) connected.add(id);
  }
  return connected;
}

// Reads each integration's SecureStore flag and writes the result into the
// Zustand store. Without this the store stays at its initial 'not-connected'
// state forever — panels persist to SecureStore but never to the store.
export async function hydrateIntegrationsFromSecureStore(): Promise<void> {
  const setStatus = useIntegrationsStore.getState().set;
  const entries = Object.entries(INTEGRATION_SECURE_KEYS) as [IntegrationId, string | null][];
  await Promise.all(
    entries.map(async ([id, key]) => {
      if (!key) return;
      const value = await SecureStore.getItemAsync(key);
      setStatus(id, value !== null ? 'connected' : 'not-connected');
    }),
  );
}

export function useHydrateIntegrations(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    hydrateIntegrationsFromSecureStore().catch(() => {});
  }, [enabled]);
}
