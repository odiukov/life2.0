import { create } from 'zustand';

export type IntegrationId =
  | 'apple-health' | 'garmin' | 'strava' | 'calendar'
  | 'ha' | 'payoneer' | 'yazio';

export type IntegrationStatus =
  | 'connected' | 'not-connected' | 'manual-upload' | 'device-only';

type IntegrationsState = {
  status: Record<IntegrationId, IntegrationStatus>;
  toggle: (id: IntegrationId) => void;
  set: (id: IntegrationId, status: IntegrationStatus) => void;
};

const initialStatus: Record<IntegrationId, IntegrationStatus> = {
  'apple-health': 'not-connected',
  garmin:         'not-connected',
  strava:         'not-connected',
  calendar:       'not-connected',
  ha:             'not-connected',
  payoneer:       'manual-upload',
  yazio:          'device-only',
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
      const next: IntegrationStatus =
        current === 'not-connected' ? 'connected' : 'not-connected';
      return { status: { ...s.status, [id]: next } };
    }),
  set: (id, status) =>
    set((s) => ({ status: { ...s.status, [id]: status } })),
}));

export function useConnectedIntegrations(): Set<IntegrationId> {
  const status = useIntegrationsStore((s) => s.status);
  const connected = new Set<IntegrationId>();
  for (const [id, st] of Object.entries(status) as [IntegrationId, IntegrationStatus][]) {
    if (isConnected(st)) connected.add(id);
  }
  return connected;
}
