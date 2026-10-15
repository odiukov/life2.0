import * as Haptics from 'expo-haptics';
import { haptic } from './haptics';

test('maps kinds to impact and notification feedback', () => {
  haptic('light');
  haptic('medium');
  haptic('success');
  haptic('warning');
  expect(Haptics.impactAsync).toHaveBeenNthCalledWith(1, 'light');
  expect(Haptics.impactAsync).toHaveBeenNthCalledWith(2, 'medium');
  expect(Haptics.notificationAsync).toHaveBeenNthCalledWith(1, 'success');
  expect(Haptics.notificationAsync).toHaveBeenNthCalledWith(2, 'warning');
});

test('a failing haptic engine is ignored', async () => {
  (Haptics.impactAsync as jest.Mock).mockRejectedValueOnce(new Error('no engine'));
  expect(() => haptic('light')).not.toThrow();
  await Promise.resolve();
});
