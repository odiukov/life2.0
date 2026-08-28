import * as SecureStore from 'expo-secure-store';
import {
  hydrateIntegrationsFromSecureStore,
  useIntegrationsStore,
  INTEGRATION_SECURE_KEYS,
} from './store';

describe('hydrateIntegrationsFromSecureStore', () => {
  beforeEach(() => {
    (SecureStore.getItemAsync as jest.Mock).mockReset();
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
