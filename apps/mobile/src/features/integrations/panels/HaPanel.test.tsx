import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';
import { ThemeProvider } from '@life-agents/ui';
import { gateway } from '@/api/gateway';
import { HaPanel } from './HaPanel';
import { useIntegrationsStore } from '../store';
jest.mock('@/api/gateway', () => ({
  gateway: { GET: jest.fn(), POST: jest.fn() },
  errorCode: (error: { detail?: string }) => error?.detail,
}));
jest.mock('@/lib/locale', () => ({ appLocale: () => 'ru' }));
const disconnected = { data: { connected: false, connected_by: null, connected_at: null } };
const connected = {
  data: { connected: true, connected_by: 'Ana', connected_at: '2026-10-14T12:00:00Z' },
};
const wrap = () =>
  render(
    <ThemeProvider>
      <HaPanel />
    </ThemeProvider>,
  );
beforeEach(() => {
  jest.clearAllMocks();
  (gateway.GET as jest.Mock).mockResolvedValue(disconnected);
});
test('family connection hides credentials and names the member', async () => {
  (gateway.GET as jest.Mock).mockResolvedValue(connected);
  wrap();
  expect(await screen.findByText(/Подключил\(а\) Ana/)).toBeTruthy();
  expect(screen.getByTestId('ha-disconnect')).toBeTruthy();
  expect(screen.queryByTestId('ha-token-input')).toBeNull();
});
test('disconnected family sees inputs and family note', async () => {
  wrap();
  await waitFor(() => expect(screen.getByTestId('ha-connect')).toBeEnabled());
  expect(screen.getByTestId('ha-token-input')).toBeTruthy();
  expect(screen.getByText('Одно подключение Home Assistant на всю семью.')).toBeTruthy();
});
test('connect refreshes server status and integration store', async () => {
  (gateway.GET as jest.Mock).mockResolvedValueOnce(disconnected).mockResolvedValue(connected);
  (gateway.POST as jest.Mock).mockResolvedValue({ data: {} });
  wrap();
  await waitFor(() => expect(screen.getByTestId('ha-connect')).toBeEnabled());
  fireEvent.changeText(screen.getByTestId('ha-base-url-input'), 'http://ha.local');
  fireEvent.changeText(screen.getByTestId('ha-token-input'), 'token');
  fireEvent.press(screen.getByTestId('ha-connect'));
  await waitFor(() => expect(useIntegrationsStore.getState().status.ha).toBe('connected'));
  expect(gateway.POST).toHaveBeenCalledWith('/integrations/ha/connect', {
    body: { base_url: 'http://ha.local', token: 'token' },
  });
  expect(gateway.GET).toHaveBeenCalledTimes(2);
});
test('connect errors show readable server detail', async () => {
  const alert = jest.spyOn(Alert, 'alert');
  (gateway.POST as jest.Mock).mockResolvedValue({
    error: { detail: 'Home Assistant rejected the token.' },
  });
  wrap();
  await waitFor(() => expect(screen.getByTestId('ha-connect')).toBeEnabled());
  fireEvent.changeText(screen.getByTestId('ha-base-url-input'), 'http://ha.local');
  fireEvent.changeText(screen.getByTestId('ha-token-input'), 'bad');
  fireEvent.press(screen.getByTestId('ha-connect'));
  await waitFor(() =>
    expect(alert).toHaveBeenCalledWith('Error', 'Home Assistant rejected the token.'),
  );
});

test('status failure after unmount does not alert', async () => {
  let reject!: (error: Error) => void;
  (gateway.GET as jest.Mock).mockReturnValue(
    new Promise((_, fail) => {
      reject = fail;
    }),
  );
  const alert = jest.spyOn(Alert, 'alert');
  const view = wrap();
  view.unmount();
  await act(async () => reject(new Error('offline')));
  expect(alert).not.toHaveBeenCalled();
});
