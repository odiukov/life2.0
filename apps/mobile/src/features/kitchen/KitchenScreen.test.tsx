import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
// eslint-disable-next-line react-native/split-platform-components
import { ActionSheetIOS } from 'react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@life-agents/ui';
import { KitchenPanel } from './KitchenScreen';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'ru' }));
const GET = jest.fn();
const POST = jest.fn();
jest.mock('@/api/gateway', () => ({
  errorCode: (e: { detail?: string }) => e?.detail ?? null,
  gateway: { GET: (...args: unknown[]) => GET(...args), POST: (...args: unknown[]) => POST(...args) },
}));

const clients: QueryClient[] = [];
const views: ReturnType<typeof render>[] = [];
function renderScreen() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { gcTime: 0 } } });
  clients.push(client);
  const view = render(<QueryClientProvider client={client}><ThemeProvider><KitchenPanel /></ThemeProvider></QueryClientProvider>);
  views.push(view);
  return view;
}

afterEach(() => {
  views.forEach((view) => view.unmount());
  views.length = 0;
  clients.forEach((client) => client.clear());
  clients.length = 0;
  jest.useRealTimers();
  jest.restoreAllMocks();
});

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  POST.mockResolvedValue({ data: { group_id: 'group-1', item: null } });
  GET.mockImplementation((path: string) => path === '/household'
    ? Promise.resolve({ data: { id: 'household-1', timezone: 'Europe/Helsinki' } })
    : Promise.resolve({ data: { items: [] } }));
});

it('consumes an item and offers the matching undo', async () => {
  GET.mockImplementation((path: string) => path === '/household'
    ? Promise.resolve({ data: { id: 'household-1', timezone: 'Europe/Lisbon' } })
    : Promise.resolve({ data: { items: [{ id: 'item-1', name: 'milk', display_name: 'milk', category: 'dairy', quantity: '1', unit: 'pcs', location: 'fridge', opened: false, opened_on: null, expires_on: '2026-10-14', expiry_source: 'explicit', added_at: '2026-10-13T00:00:00Z', added_by: null }] } }));
  const sheet = jest.spyOn(ActionSheetIOS, 'showActionSheetWithOptions').mockImplementation((_options, callback) => callback(0));
  renderScreen();
  fireEvent.press(await screen.findByText('milk'));
  await waitFor(() => expect(POST).toHaveBeenCalledWith('/kitchen/items/{item_id}/action', expect.objectContaining({ body: { action: 'consumed' } })));
  fireEvent.press(await screen.findByText('Отменить'));
  await waitFor(() => expect(POST).toHaveBeenCalledWith('/kitchen/undo/{group_id}', expect.objectContaining({ params: { path: { group_id: 'group-1' } } })));
  sheet.mockRestore();
});

it('shows items with household-zone expiry and estimate mark', async () => {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Europe/Helsinki', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date());
  const field = (type: string) => parts.find((part) => part.type === type)?.value;
  const expiresOn = `${field('year')}-${field('month')}-${field('day')}`;
  GET.mockImplementation((path: string) => path === '/household'
    ? Promise.resolve({ data: { id: 'household-1', timezone: 'Europe/Helsinki' } })
    : Promise.resolve({ data: { items: [{ id: '1', name: 'milk', display_name: 'milk 3.2%', category: 'dairy', quantity: '1000', unit: 'ml', location: 'fridge', opened: false, opened_on: null, expires_on: expiresOn, expiry_source: 'estimated', added_at: '2026-10-13T00:00:00Z', added_by: null }] } }));
  renderScreen();
  expect(await screen.findByText('milk 3.2%')).toBeTruthy();
  expect(screen.getByText('≈ сегодня')).toBeTruthy();
});

it('shows empty hint', async () => {
  renderScreen();
  expect(await screen.findByText('Здесь пусто. Скажи в чат: «купил молоко».')).toBeTruthy();
});

it('shows unavailable state', async () => {
  GET.mockImplementation((path: string) => path === '/household'
    ? Promise.resolve({ data: { id: 'household-1', timezone: 'Europe/Lisbon' } })
    : Promise.resolve({ error: { detail: 'kitchen_unavailable' } }));
  renderScreen();
  expect(await screen.findByText('Кухня временно недоступна.')).toBeTruthy();
});
