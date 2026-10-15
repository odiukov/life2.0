import React from 'react';
import { act, render, screen, waitFor } from '@testing-library/react-native';
import * as Linking from 'expo-linking';
import RootLayout from '../../../app/_layout';
import { useTaskSheet } from './sheetStore';
import { TaskSheet } from './TaskSheet';
import { fakeTasksApi } from '@/features/chat/fakeTasksApi';
import * as SecureStore from 'expo-secure-store';

let mockSessionState: { ready: boolean; session: { user: { id: string } } | null };
let mockSegments: string[];
const mockApi = fakeTasksApi();
const mockPush = jest.fn();
const mockReplace = jest.fn();

jest.mock('expo-router', () => {
  const { View } = jest.requireActual('react-native');
  const Stack = ({ children }: { children: React.ReactNode }) => (
    <View testID="root-stack">{mockSegments[0] === '(tabs)' ? <TaskSheet /> : children}</View>
  );
  Stack.Screen = function MockScreen() { return null; };
  const router = {
    push: (...args: unknown[]) => mockPush(...args),
    replace: (...args: unknown[]) => mockReplace(...args),
  };
  return { Stack, router, useRouter: () => router, useSegments: () => mockSegments };
});
jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('@/features/auth/useSession', () => ({ useSession: () => mockSessionState }));
jest.mock('@/features/integrations/store', () => ({
  useHydrateIntegrations: jest.fn(),
  useConnectedIntegrations: () => new Set(),
}));
jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('@/features/chat/tasksApi', () => ({
  ...jest.requireActual('@/features/chat/tasksApi'),
  defaultTasksApi: () => mockApi,
}));
jest.mock('@/features/inbox/InboxScreen', () => ({
  NOTIFICATION_ROUTES: { '/kitchen': '/(tabs)/house' },
}));
jest.mock('@/features/inbox/registerPush', () => ({ usePushRegistration: jest.fn() }));
jest.mock('@/features/healthkit/background', () => ({ registerBackgroundSync: jest.fn() }));
jest.mock('@/features/healthkit/sync', () => ({ runSync: jest.fn() }));
jest.mock('@/features/sync/serverSync', () => ({ triggerServerSync: jest.fn() }));

beforeEach(async () => {
  await SecureStore.deleteItemAsync('open_task_id');
  jest.clearAllMocks();
  useTaskSheet.getState().hide();
  mockSessionState = { ready: false, session: null };
  mockSegments = [];
  jest.spyOn(Linking, 'getInitialURL').mockResolvedValue('lifeagents://share?file');
  jest
    .spyOn(Linking, 'parse')
    .mockReturnValue({
      queryParams: { shareFileURL: 'file:///statement.pdf', shareFileName: 'statement.pdf' },
    } as never);
});

test('a cold share queues before session restoration and navigates once after the navigator mounts', async () => {
  const view = render(<RootLayout />);
  await waitFor(() =>
    expect(useTaskSheet.getState().pending?.attachments).toEqual([
      { uri: 'file:///statement.pdf', name: 'statement.pdf', mime: 'application/pdf', size: 0 },
    ]),
  );
  expect(screen.queryByTestId('root-stack')).toBeNull();
  expect(mockPush).not.toHaveBeenCalled();
  mockSessionState = { ready: true, session: { user: { id: 'u1' } } };
  view.rerender(<RootLayout />);
  expect(screen.getByTestId('root-stack')).toBeTruthy();
  expect(mockPush).not.toHaveBeenCalled();
  mockSegments = ['inbox'];
  view.rerender(<RootLayout />);
  await waitFor(() => expect(mockPush).toHaveBeenCalledWith('/(tabs)'));
  view.rerender(<RootLayout />);
  expect(mockPush).toHaveBeenCalledTimes(1);
  expect(useTaskSheet.getState().queue).toHaveLength(1);
  expect(Linking.getInitialURL).toHaveBeenCalledTimes(1);
  mockSegments = ['(tabs)'];
  view.rerender(<RootLayout />);
  expect(await screen.findByText('statement.pdf')).toBeTruthy();
  expect(screen.getAllByText('statement.pdf')).toHaveLength(1);
  await waitFor(() => expect(useTaskSheet.getState().queue).toHaveLength(0));
  expect(mockApi.open).not.toHaveBeenCalled();
  expect(mockPush).toHaveBeenCalledTimes(1);
});

test('a cold share survives sign-in and uses the auth redirect without duplicate navigation', async () => {
  const view = render(<RootLayout />);
  await waitFor(() => expect(useTaskSheet.getState().queue).toHaveLength(1));
  mockSessionState = { ready: true, session: null };
  mockSegments = ['(auth)', 'sign-in'];
  view.rerender(<RootLayout />);
  expect(mockPush).not.toHaveBeenCalled();
  expect(mockReplace).not.toHaveBeenCalled();
  mockSessionState = { ready: true, session: { user: { id: 'u1' } } };
  view.rerender(<RootLayout />);
  await waitFor(() => expect(mockReplace).toHaveBeenCalledWith('/(tabs)'));
  expect(mockReplace).toHaveBeenCalledTimes(1);
  expect(mockPush).not.toHaveBeenCalled();
  expect(useTaskSheet.getState().queue).toHaveLength(1);
  await act(async () => undefined);
});
