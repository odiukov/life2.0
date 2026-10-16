import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@life-agents/ui';
import { router } from 'expo-router';
import { InboxScreen } from './InboxScreen';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'ru' }));
const GET = jest.fn();
const POST = jest.fn();
jest.mock('@/api/gateway', () => ({ gateway: { GET: (...args: unknown[]) => GET(...args), POST: (...args: unknown[]) => POST(...args) } }));
const sessionState = { session: { user: { id: 'alice' } } as { user: { id: string } } | null };
jest.mock('@/features/auth/useSession', () => ({ useSession: (selector?: (state: typeof sessionState) => unknown) => selector ? selector(sessionState) : sessionState }));

const item = { id: 'n1', kind: 'kitchen.digest', title: 'Пора проверить продукты', body: 'курица (завтра)', data: { route: '/kitchen' }, created_at: '2026-10-14T18:00:00Z', read_at: null };
const clients: QueryClient[] = [];
const views: ReturnType<typeof render>[] = [];
function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  clients.push(client);
  const view = render(<QueryClientProvider client={client}><ThemeProvider><InboxScreen /></ThemeProvider></QueryClientProvider>);
  views.push(view);
  return { client, view };
}

beforeEach(() => {
  jest.clearAllMocks();
  sessionState.session = { user: { id: 'alice' } };
  GET.mockResolvedValue({ data: { unread_count: 1, items: [item] } });
  POST.mockResolvedValue({ data: undefined });
});
afterEach(() => {
  views.forEach((view) => view.unmount());
  views.length = 0;
  clients.forEach((client) => client.clear());
  clients.length = 0;
});

it('marks an item read and opens its app route', async () => {
  renderScreen();
  fireEvent.press(await screen.findByText(item.title));
  await waitFor(() => expect(POST).toHaveBeenCalledWith('/notifications/{notification_id}/read', { params: { path: { notification_id: 'n1' } } }));
  await waitFor(() => expect(router.push).toHaveBeenCalledWith('/(tabs)?agent=kitchen'));
});

it('surfaces a mark-read error and does not navigate', async () => {
  POST.mockResolvedValueOnce({ error: { detail: 'failure' } });
  renderScreen();
  fireEvent.press(await screen.findByText(item.title));
  await screen.findByText('Не удалось обновить уведомления.');
  expect(router.push).not.toHaveBeenCalled();
});

it('surfaces a read-all error', async () => {
  POST.mockResolvedValueOnce({ error: { detail: 'failure' } });
  renderScreen();
  fireEvent.press(await screen.findByText('Прочитать все'));
  await screen.findByText('Не удалось обновить уведомления.');
});

it('isolates query data when the authenticated account changes', async () => {
  const { view } = renderScreen();
  await screen.findByText(item.title);
  GET.mockResolvedValue({ data: { unread_count: 0, items: [] } });
  sessionState.session = { user: { id: 'bob' } };
  view.rerender(<QueryClientProvider client={clients[0]!}><ThemeProvider><InboxScreen /></ThemeProvider></QueryClientProvider>);
  await screen.findByText('Пока ничего нет.');
  expect(screen.queryByText(item.title)).toBeNull();
});
