// Jest mock for expo-web-browser
export const openAuthSessionAsync = jest.fn(async () => ({ type: 'cancel' as const }));
export const openBrowserAsync = jest.fn(async () => ({ type: 'cancel' as const }));
export const dismissBrowser = jest.fn();
export const mayInitWithUrlAsync = jest.fn(async () => {});
export const warmUpAsync = jest.fn(async () => {});
export const coolDownAsync = jest.fn(async () => {});
