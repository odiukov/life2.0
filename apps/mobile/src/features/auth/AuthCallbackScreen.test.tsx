import React from 'react';
import { render, waitFor } from '@testing-library/react-native';
import * as Linking from 'expo-linking';
import AuthCallbackScreen from './AuthCallbackScreen';

const completeSignIn = jest.fn();
jest.mock('./useSession', () => ({ useSession: { getState: () => ({ completeSignIn }) } }));
jest.mock('expo-linking', () => ({
  getInitialURL: jest.fn(),
  addEventListener: jest.fn(() => ({ remove: jest.fn() })),
}));

test('exchanges a cold-start ticket without logging it', async () => {
  jest
    .mocked(Linking.getInitialURL)
    .mockResolvedValue('lifeagents://auth-callback?ticket=private-ticket');
  completeSignIn.mockResolvedValue(undefined);
  const log = jest.spyOn(console, 'log').mockImplementation(() => {});
  try {
    render(<AuthCallbackScreen />);
    await waitFor(() => expect(completeSignIn).toHaveBeenCalledWith('private-ticket'));
    expect(log.mock.calls.flat().join(' ')).not.toContain('private-ticket');
  } finally {
    log.mockRestore();
  }
});
