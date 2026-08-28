// Jest mock for expo-task-manager
export const defineTask = jest.fn((_name: string, _task: unknown) => {});
export const isTaskRegisteredAsync = jest.fn(async () => false);
export const getRegisteredTasksAsync = jest.fn(async () => []);
export const unregisterAllTasksAsync = jest.fn(async () => {});
export const unregisterTaskAsync = jest.fn(async () => {});
