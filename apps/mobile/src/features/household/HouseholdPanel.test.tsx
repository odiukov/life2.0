import React from 'react';
import { Alert, Share } from 'react-native';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@life-agents/ui';
import { gateway } from '@/api/gateway';
import { HouseholdPanel } from './HouseholdPanel';
import { HOUSEHOLD_KEY, type Household } from './useHousehold';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'ru' }));
jest.mock('@/api/gateway', () => {
  const household = {
    id: 'h',
    name: 'Дыковы',
    timezone: 'Europe/Lisbon',
    digest_time: '18:00',
    my_role: 'owner',
    members: [
      { user_id: 'a', name: 'Аня', role: 'owner', joined_at: '2026-10-14T00:00:00Z' },
      { user_id: 'b', name: 'Боря', role: 'member', joined_at: '2026-10-14T01:00:00Z' },
    ],
  };
  return {
    errorCode: (error: { detail?: string }) => error?.detail ?? null,
    gateway: {
      GET: jest.fn(async () => ({ data: household })),
      POST: jest.fn(async (path: string) =>
        path === '/household/invites'
          ? { data: { code: 'ABCD-EF12', expires_at: '2026-10-16T00:00:00Z' } }
          : path === '/household/join/preview'
            ? { error: { detail: 'invite_invalid' } }
            : { data: household },
      ),
      PATCH: jest.fn(async () => ({ data: household })),
      DELETE: jest.fn(async () => ({ data: undefined })),
    },
  };
});

const clients: QueryClient[] = [];

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity }, mutations: { gcTime: 0 } },
  });
  clients.push(client);
  const view = render(
    <QueryClientProvider client={client}>
      <ThemeProvider>
        <HouseholdPanel />
      </ThemeProvider>
    </QueryClientProvider>,
  );
  return { client, ...view };
}

afterEach(() => {
  clients.forEach((client) => client.clear());
  clients.length = 0;
  jest.restoreAllMocks();
});

it('lists members with the owner marked', async () => {
  renderPanel();
  expect(await screen.findByText('Дыковы')).toBeTruthy();
  expect(screen.getByText('Аня · владелец')).toBeTruthy();
  expect(screen.getByText('Боря')).toBeTruthy();
});

it('shows an invite code and shares a localized message', async () => {
  renderPanel();
  fireEvent.press(await screen.findByText('Пригласить'));
  expect(await screen.findByText('ABCD-EF12')).toBeTruthy();
  const share = jest.spyOn(Share, 'share').mockResolvedValue({ action: Share.sharedAction });
  fireEvent.press(screen.getByText('Поделиться'));
  expect(share).toHaveBeenCalledWith({
    message: 'Присоединяйся к нашему дому в Life Agents: код ABCD-EF12',
  });
});

it('maps join preview errors to localized text', async () => {
  renderPanel();
  fireEvent.changeText(await screen.findByPlaceholderText('XXXX-XXXX'), 'zzzz-zzzz');
  fireEvent.press(screen.getByText('Вступить'));
  await waitFor(() => expect(screen.getByText('Код не подошёл или уже использован.')).toBeTruthy());
});

it('asks for confirmation before removing a member', async () => {
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
  renderPanel();
  await screen.findByText('Дыковы');
  fireEvent.press(screen.getByText('Исключить'));
  expect(alert).toHaveBeenCalledWith('Исключить', 'Исключить Боря из дома?', expect.any(Array));
});

it('hides an invitation from the previous household when household data changes', async () => {
  const { client } = renderPanel();
  fireEvent.press(await screen.findByText('Пригласить'));
  expect(await screen.findByText('ABCD-EF12')).toBeTruthy();

  const previous = client.getQueryData<Household>(HOUSEHOLD_KEY);
  expect(previous).toBeDefined();
  act(() => {
    client.setQueryData(HOUSEHOLD_KEY, { ...previous, id: 'h2', name: 'Другой дом' });
  });
  expect(await screen.findByText('Другой дом')).toBeTruthy();
  await waitFor(() => expect(screen.queryByText('ABCD-EF12')).toBeNull());
  expect(screen.queryByText('Поделиться')).toBeNull();
});

it('confirms a join, shows moved items, and clears the old invitation', async () => {
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
  renderPanel();
  fireEvent.press(await screen.findByText('Пригласить'));
  await screen.findByText('ABCD-EF12');
  const post = gateway.POST as jest.Mock;
  post
    .mockImplementationOnce(async () => ({
      data: { household_name: 'Новый дом', member_count: 3, items_to_move: 2 },
    }))
    .mockImplementationOnce(async () => ({
      data: {
        id: 'h2',
        name: 'Новый дом',
        my_role: 'member',
        members: [],
        timezone: 'Europe/Lisbon',
        digest_time: '18:00',
      },
    }));

  fireEvent.changeText(screen.getByPlaceholderText('XXXX-XXXX'), 'wxyz-2345');
  fireEvent.press(screen.getByText('Вступить'));
  await waitFor(() => expect(alert).toHaveBeenCalled());
  const confirmation = alert.mock.calls.at(-1);
  expect(confirmation?.[1]).toContain('Твои 2 продукта переедут туда.');
  act(() => confirmation?.[2]?.[1]?.onPress?.());

  expect(await screen.findByText('Новый дом')).toBeTruthy();
  await waitFor(() => expect(screen.queryByText('ABCD-EF12')).toBeNull());
  expect(screen.getByPlaceholderText('XXXX-XXXX').props.value).toBe('');
});

it('confirms leave and clears the previous invitation', async () => {
  const alert = jest.spyOn(Alert, 'alert').mockImplementation(() => undefined);
  renderPanel();
  fireEvent.press(await screen.findByText('Пригласить'));
  await screen.findByText('ABCD-EF12');
  (gateway.POST as jest.Mock).mockImplementationOnce(async () => ({
    data: {
      id: 'h3',
      name: 'Новый пустой дом',
      my_role: 'owner',
      members: [],
      timezone: 'Europe/Lisbon',
      digest_time: '18:00',
    },
  }));

  fireEvent.press(screen.getByText('Выйти из дома'));
  const confirmation = alert.mock.calls.at(-1);
  expect(confirmation?.[1]).toBe('Выйти? У тебя будет новый пустой дом.');
  act(() => confirmation?.[2]?.[1]?.onPress?.());

  expect(await screen.findByText('Новый пустой дом')).toBeTruthy();
  await waitFor(() => expect(screen.queryByText('ABCD-EF12')).toBeNull());
});
