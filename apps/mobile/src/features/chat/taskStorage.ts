import * as SecureStore from 'expo-secure-store';

const KEY = 'open_task_id';

export const loadOpenTaskId = () => SecureStore.getItemAsync(KEY);
export const saveOpenTaskId = (id: string) => SecureStore.setItemAsync(KEY, id);
export const clearOpenTaskId = () => SecureStore.deleteItemAsync(KEY);
