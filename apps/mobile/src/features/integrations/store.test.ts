import { gateway } from '@/api/gateway';
jest.mock('@/api/gateway', () => ({ gateway: { GET: jest.fn() } }));
import * as SecureStore from 'expo-secure-store';
import {
  hydrateIntegrationsFromSecureStore,
  useIntegrationsStore,
  INTEGRATION_SECURE_KEYS,
} from './store';

describe('hydrateIntegrationsFromSecureStore', () => {
  beforeEach(() => {
    (SecureStore.getItemAsync as jest.Mock).mockReset();
    (gateway.GET as jest.Mock).mockResolvedValue({ data: { connected: false } });
    useIntegrationsStore.setState({
      status: {
        'apple-health': 'not-connected',
        garmin: 'not-connected',
        strava: 'not-connected',
        calendar: 'not-connected',
        ha: 'not-connected',
        payoneer: 'manual-upload',
        yazio: 'device-only',
      },
    });
  });

  it('marks integrations whose SecureStore key is present as connected', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockImplementation(async (key: string) => {
      if (key === INTEGRATION_SECURE_KEYS['apple-health']) return '2026-04-29T12:00:00Z';
      if (key === INTEGRATION_SECURE_KEYS.garmin) return '1';
      return null;
    });

    await hydrateIntegrationsFromSecureStore();

    const status = useIntegrationsStore.getState().status;
    expect(status['apple-health']).toBe('connected');
    expect(status.garmin).toBe('connected');
    expect(status.yazio).toBe('not-connected');
    expect(status.calendar).toBe('not-connected');
    expect(status.ha).toBe('not-connected');
  });

  it('does not touch integrations without a SecureStore key (strava, payoneer)', async () => {
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);

    await hydrateIntegrationsFromSecureStore();

    const status = useIntegrationsStore.getState().status;
    expect(status.strava).toBe('not-connected'); // initial preserved
    expect(status.payoneer).toBe('manual-upload'); // initial preserved
  });

  it('flips a previously connected integration back to not-connected when key is gone', async () => {
    useIntegrationsStore.getState().set('garmin', 'connected');
    (SecureStore.getItemAsync as jest.Mock).mockResolvedValue(null);

    await hydrateIntegrationsFromSecureStore();

    expect(useIntegrationsStore.getState().status.garmin).toBe('not-connected');
  });
});

test('HA hydration uses family status and removes the stale flag', async () => {
  (gateway.GET as jest.Mock).mockResolvedValue({ data: { connected: true } });
  await hydrateIntegrationsFromSecureStore();
  expect(gateway.GET).toHaveBeenCalledWith('/integrations/ha/status');
  expect(useIntegrationsStore.getState().status.ha).toBe('connected');
  expect(SecureStore.deleteItemAsync).toHaveBeenCalledWith('ha_connected');
});
test('failed HA status leaves it disconnected', async () => {
  useIntegrationsStore.getState().set('ha', 'connected');
  (gateway.GET as jest.Mock).mockRejectedValue(new Error('offline'));
  await hydrateIntegrationsFromSecureStore();
  expect(useIntegrationsStore.getState().status.ha).toBe('not-connected');
});

test('local integration hydration completes while HA status remains pending', async () => {
  let finish!: (value: unknown) => void;
  (gateway.GET as jest.Mock).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  (SecureStore.getItemAsync as jest.Mock).mockResolvedValue('1');
  useIntegrationsStore.getState().set('garmin', 'not-connected');
  const hydration = hydrateIntegrationsFromSecureStore();
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(useIntegrationsStore.getState().status.garmin).toBe('connected');
  finish({ data: { connected: false } });
  await hydration;
});
