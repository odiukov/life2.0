import * as BackgroundFetch from 'expo-background-fetch';
import * as TaskManager from 'expo-task-manager';
import { runSync } from './sync';

const TASK = 'hk-background-sync';

TaskManager.defineTask(TASK, async () => {
  try {
    await runSync();
    return BackgroundFetch.BackgroundFetchResult.NewData;
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed;
  }
});

export async function registerBackgroundSync() {
  await BackgroundFetch.registerTaskAsync(TASK, {
    minimumInterval: 30 * 60,
    stopOnTerminate: false,
    startOnBoot: true,
  });
}
