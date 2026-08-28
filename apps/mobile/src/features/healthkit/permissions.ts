/**
 * HealthKit permissions.
 *
 * Package: @kingstinct/react-native-healthkit (v14)
 * Why chosen: actively maintained, Expo config-plugin included, Nitro-modules
 * based for SDK 54 new-arch support, peer deps satisfied (RN >=0.79, React >=19).
 *
 * On Expo Go / non-iOS the native module is absent; we detect that and return
 * false so the rest of the app still renders without crashing.
 */

import { HK_QUANTITY_TYPES, HK_CATEGORY_TYPES, HK_WORKOUT_TYPE } from './types';

function isHealthKitAvailable(): boolean {
  try {
    // The package exports isHealthDataAvailable which returns false on Android
    // and throws (or returns false) when the native module isn't loaded.
    const hk = require('@kingstinct/react-native-healthkit') as {
      isHealthDataAvailable: () => boolean;
    };
    return typeof hk.isHealthDataAvailable === 'function' && hk.isHealthDataAvailable();
  } catch {
    return false;
  }
}

/**
 * Request read permissions for all tracked HealthKit types.
 * Returns true if permissions were granted, false if HealthKit is unavailable
 * or the user denied.
 */
export async function requestPermissions(): Promise<boolean> {
  if (!isHealthKitAvailable()) {
    console.warn('[HealthKit] HealthKit unavailable — skipping permission request.');
    return false;
  }

  try {
    const { requestAuthorization } = require('@kingstinct/react-native-healthkit') as {
      requestAuthorization: (req: {
        toRead?: readonly string[];
        toShare?: readonly string[];
      }) => Promise<boolean>;
    };

    const granted = await requestAuthorization({
      toRead: [...HK_QUANTITY_TYPES, ...HK_CATEGORY_TYPES, HK_WORKOUT_TYPE],
      toShare: [],
    });
    return granted;
  } catch (err) {
    console.warn('[HealthKit] requestAuthorization failed:', err);
    return false;
  }
}
