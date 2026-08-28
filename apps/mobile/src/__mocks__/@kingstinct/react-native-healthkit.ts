// Jest mock for @kingstinct/react-native-healthkit
export const isHealthDataAvailable = jest.fn(() => false);
export const isHealthDataAvailableAsync = jest.fn(async () => false);
export const requestAuthorization = jest.fn(async () => false);
export const queryQuantitySamples = jest.fn(async () => []);
export const queryCategorySamples = jest.fn(async () => []);
export const queryWorkoutSamples = jest.fn(async () => []);
export const getRequestStatusForAuthorization = jest.fn(async () => 0);

export default {
  isHealthDataAvailable,
  isHealthDataAvailableAsync,
  requestAuthorization,
  queryQuantitySamples,
  queryCategorySamples,
  queryWorkoutSamples,
  getRequestStatusForAuthorization,
};
