import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { ActionCard } from './ActionCard';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'ru' }));
const NOW = Date.parse('2026-10-14T18:00:00Z');
const pending = {
  id: 'a1',
  summary: 'Выключить: Lamp?',
  expiresAt: '2026-10-14T18:05:00Z',
  status: 'pending' as const,
};
const wrap = (ui: React.ReactElement) => render(<ThemeProvider>{ui}</ThemeProvider>);

test('pending: summary, countdown and both buttons; a tap disables both', () => {
  const onConfirm = jest.fn();
  wrap(<ActionCard action={pending} onConfirm={onConfirm} onReject={jest.fn()} now={() => NOW} />);
  expect(screen.getByText('Выключить: Lamp?')).toBeTruthy();
  expect(screen.getByText(/5:00/)).toBeTruthy();
  fireEvent.press(screen.getByTestId('action-confirm'));
  fireEvent.press(screen.getByTestId('action-confirm'));
  expect(onConfirm).toHaveBeenCalledTimes(1);
  expect(screen.getByTestId('action-reject')).toBeDisabled();
});

test('past expiresAt shows expired without buttons', () => {
  wrap(
    <ActionCard
      action={pending}
      onConfirm={jest.fn()}
      onReject={jest.fn()}
      now={() => NOW + 6 * 60_000}
    />,
  );
  expect(screen.getByText('Время на подтверждение вышло')).toBeTruthy();
  expect(screen.queryByTestId('action-confirm')).toBeNull();
});

test.each([
  ['applied', 'Готово.', 'Готово.'],
  ['rejected', 'Отменено.', 'Отменено.'],
  ['failed', 'Home Assistant сейчас недоступен.', 'Home Assistant сейчас недоступен.'],
])('final state %s shows the server message', (status, message, shown) => {
  wrap(
    <ActionCard
      action={{ ...pending, status: status as never, message }}
      onConfirm={jest.fn()}
      onReject={jest.fn()}
      now={() => NOW}
    />,
  );
  expect(screen.getByText(shown)).toBeTruthy();
  expect(screen.queryByTestId('action-confirm')).toBeNull();
});

test('an asynchronous decision that leaves the action pending can be retried', async () => {
  const confirm = jest.fn(async () => undefined);
  wrap(<ActionCard action={pending} onConfirm={confirm} onReject={jest.fn()} now={() => NOW} />);
  await act(async () => {
    fireEvent.press(screen.getByTestId('action-confirm'));
  });
  expect(screen.getByTestId('action-confirm')).not.toBeDisabled();
});

test('an applying action shows progress without decision buttons', () => {
  wrap(
    <ActionCard
      action={{ ...pending, status: 'applying' }}
      onConfirm={jest.fn()}
      onReject={jest.fn()}
      now={() => NOW}
    />,
  );
  expect(screen.getByText('Выполняется…')).toBeTruthy();
  expect(screen.queryByTestId('action-confirm')).toBeNull();
});
