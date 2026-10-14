export const getPermissionsAsync = jest.fn(async () => ({ granted: true, canAskAgain: true }));
export const requestPermissionsAsync = jest.fn(async () => ({ granted: true }));
export const getExpoPushTokenAsync = jest.fn(async () => ({ data: 'ExponentPushToken[mock]' }));
export const setNotificationHandler = jest.fn();
export const addNotificationResponseReceivedListener = jest.fn(() => ({ remove: jest.fn() }));
export const getLastNotificationResponseAsync = jest.fn(async () => null);
