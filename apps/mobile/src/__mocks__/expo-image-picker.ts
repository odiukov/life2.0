export const launchCameraAsync = jest.fn(async () => ({ canceled: true, assets: null }));
export const launchImageLibraryAsync = jest.fn(async () => ({ canceled: true, assets: null }));
export const requestCameraPermissionsAsync = jest.fn(async () => ({ granted: true }));
