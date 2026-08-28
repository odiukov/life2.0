// Jest mock for expo-background-fetch
export enum BackgroundFetchResult {
  NoData = 1,
  NewData = 2,
  Failed = 3,
}

export const registerTaskAsync = jest.fn(async () => {});
export const unregisterTaskAsync = jest.fn(async () => {});
export const getStatusAsync = jest.fn(async () => 3); // Available = 3
export const setMinimumIntervalAsync = jest.fn(async () => {});
