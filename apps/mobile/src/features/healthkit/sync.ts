/**
 * HealthKit sync.
 *
 * Reads samples from HealthKit and uploads them to POST /sync/health.
 * Persists the last-sync timestamp in expo-secure-store.
 * Gracefully no-ops when HealthKit is not available (Android, Expo Go).
 */

import * as SecureStore from 'expo-secure-store';
import { apiBaseUrl } from '@/api/client';
import { supabase, SUPABASE_CONFIGURED } from '@/features/auth/SupabaseClient';
import { useSyncTimestamp } from '@/features/sync/syncTimestamp';
import type { HealthSample, HealthKitReadType } from './types';
import { HK_QUANTITY_TYPES, HK_CATEGORY_TYPES } from './types';

const LAST_SYNC_KEY = 'hk_last_sync';
const SOURCES_SEEN_KEY = 'hk_sources_seen';
const CHUNK_SIZE = 500;
const LOOKBACK_DAYS = 90;
const MIN_SYNC_INTERVAL_MS = 5 * 60 * 1000;

// ---- helpers ----------------------------------------------------------------

async function persistDistinctSources(samples: HealthSample[]): Promise<void> {
  const seen = new Set<string>();
  for (const s of samples) {
    if (s.source) seen.add(s.source);
  }
  if (seen.size === 0) return;
  try {
    const existingRaw = await SecureStore.getItemAsync(SOURCES_SEEN_KEY);
    const existing: string[] = existingRaw ? JSON.parse(existingRaw) : [];
    for (const v of existing) seen.add(v);
    await SecureStore.setItemAsync(SOURCES_SEEN_KEY, JSON.stringify([...seen].sort()));
  } catch {
    // Cache corruption is non-fatal — overwrite with current set.
    await SecureStore.setItemAsync(SOURCES_SEEN_KEY, JSON.stringify([...seen].sort()));
  }
}

export async function getDetectedSources(): Promise<string[]> {
  try {
    const raw = await SecureStore.getItemAsync(SOURCES_SEEN_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function daysAgo(n: number): Date {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d;
}

function isHealthKitAvailable(): boolean {
  try {
    const hk = require('@kingstinct/react-native-healthkit') as {
      isHealthDataAvailable: () => boolean;
    };
    return typeof hk.isHealthDataAvailable === 'function' && hk.isHealthDataAvailable();
  } catch {
    return false;
  }
}

export async function getAuthHeaders(): Promise<Record<string, string>> {
  if (!SUPABASE_CONFIGURED) return {};
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function postChunk(samples: HealthSample[]): Promise<void> {
  const headers = await getAuthHeaders();
  const res = await fetch(`${apiBaseUrl}/sync/health`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...headers },
    body: JSON.stringify({ samples }),
  });
  if (!res.ok) {
    throw new Error(`POST /sync/health failed: ${res.status}`);
  }
}

// ---- quantity-value normaliser ---------------------------------------------

// kingstinct v14 returns HealthKit quantities as { quantity, unit } objects
// in some paths (workout totals) and plain numbers in others.
type HKQuantityLike = number | { quantity: number; unit?: string } | null | undefined;

function toNumber(v: HKQuantityLike): number {
  if (v == null) return 0;
  if (typeof v === 'number') return v;
  if (typeof v === 'object' && 'quantity' in v && typeof v.quantity === 'number') {
    return v.quantity;
  }
  return 0;
}

// ---- quantity sample reader -------------------------------------------------

type HKQuantitySample = {
  startDate: Date | string;
  endDate: Date | string;
  quantity: number | { quantity: number; unit?: string };
  unit?: string;
  sourceRevision?: { source?: { name?: string } };
};

type HKCategorySample = {
  startDate: Date | string;
  endDate: Date | string;
  value: number | { quantity: number; unit?: string };
  sourceRevision?: { source?: { name?: string } };
};

function toISO(d: Date | string): string {
  return typeof d === 'string' ? d : d.toISOString();
}

function sourceName(sample: HKQuantitySample | HKCategorySample): string {
  return sample.sourceRevision?.source?.name ?? 'HealthKit';
}

/** Map HK identifier → backend short name */
const QUANTITY_TYPE_MAP: Record<(typeof HK_QUANTITY_TYPES)[number], HealthKitReadType> = {
  // vitals
  HKQuantityTypeIdentifierHeartRate: 'heartRate',
  HKQuantityTypeIdentifierRestingHeartRate: 'restingHeartRate',
  HKQuantityTypeIdentifierWalkingHeartRateAverage: 'walkingHeartRateAverage',
  HKQuantityTypeIdentifierHeartRateVariabilitySDNN: 'heartRateVariabilitySDNN',
  HKQuantityTypeIdentifierOxygenSaturation: 'oxygenSaturation',
  HKQuantityTypeIdentifierRespiratoryRate: 'respiratoryRate',
  HKQuantityTypeIdentifierBodyTemperature: 'bodyTemperature',
  HKQuantityTypeIdentifierAppleSleepingWristTemperature: 'sleepingWristTemperature',
  HKQuantityTypeIdentifierBloodPressureSystolic: 'bloodPressureSystolic',
  HKQuantityTypeIdentifierBloodPressureDiastolic: 'bloodPressureDiastolic',
  HKQuantityTypeIdentifierBloodGlucose: 'bloodGlucose',
  HKQuantityTypeIdentifierVO2Max: 'vo2Max',
  HKQuantityTypeIdentifierAtrialFibrillationBurden: 'atrialFibrillationBurden',
  // body
  HKQuantityTypeIdentifierBodyMass: 'bodyMass',
  HKQuantityTypeIdentifierHeight: 'height',
  HKQuantityTypeIdentifierBodyMassIndex: 'bodyMassIndex',
  HKQuantityTypeIdentifierBodyFatPercentage: 'bodyFatPercentage',
  HKQuantityTypeIdentifierLeanBodyMass: 'leanBodyMass',
  HKQuantityTypeIdentifierWaistCircumference: 'waistCircumference',
  // activity
  HKQuantityTypeIdentifierActiveEnergyBurned: 'activeEnergyBurned',
  HKQuantityTypeIdentifierBasalEnergyBurned: 'basalEnergyBurned',
  HKQuantityTypeIdentifierStepCount: 'stepCount',
  HKQuantityTypeIdentifierFlightsClimbed: 'flightsClimbed',
  HKQuantityTypeIdentifierAppleExerciseTime: 'exerciseTime',
  HKQuantityTypeIdentifierWorkoutEffortScore: 'workoutEffortScore',
  HKQuantityTypeIdentifierPhysicalEffort: 'physicalEffort',
  HKQuantityTypeIdentifierNumberOfTimesFallen: 'timesFallen',
  HKQuantityTypeIdentifierAppleWalkingSteadiness: 'walkingSteadiness',
  HKQuantityTypeIdentifierTimeInDaylight: 'timeInDaylight',
  // distances
  HKQuantityTypeIdentifierDistanceWalkingRunning: 'distanceWalkingRunning',
  HKQuantityTypeIdentifierDistanceCycling: 'distanceCycling',
  HKQuantityTypeIdentifierDistanceSwimming: 'distanceSwimming',
  HKQuantityTypeIdentifierDistanceCrossCountrySkiing: 'distanceCrossCountrySkiing',
  HKQuantityTypeIdentifierDistanceDownhillSnowSports: 'distanceDownhillSnowSports',
  HKQuantityTypeIdentifierDistancePaddleSports: 'distancePaddleSports',
  HKQuantityTypeIdentifierDistanceRowing: 'distanceRowingSports',
  HKQuantityTypeIdentifierDistanceWheelchair: 'distanceWheelchair',
  HKQuantityTypeIdentifierSixMinuteWalkTestDistance: 'sixMinuteWalkTestDistance',
  // gait
  HKQuantityTypeIdentifierWalkingSpeed: 'walkingSpeed',
  HKQuantityTypeIdentifierWalkingStepLength: 'walkingStepLength',
  HKQuantityTypeIdentifierWalkingDoubleSupportPercentage: 'walkingDoubleSupportPercentage',
  HKQuantityTypeIdentifierWalkingAsymmetryPercentage: 'walkingAsymmetryPercentage',
  HKQuantityTypeIdentifierStairAscentSpeed: 'stairAscentSpeed',
  HKQuantityTypeIdentifierStairDescentSpeed: 'stairDescentSpeed',
  // running biomechanics
  HKQuantityTypeIdentifierRunningSpeed: 'runningSpeed',
  HKQuantityTypeIdentifierRunningPower: 'runningPower',
  HKQuantityTypeIdentifierRunningGroundContactTime: 'runningGroundContactTime',
  HKQuantityTypeIdentifierRunningStrideLength: 'runningStrideLength',
  HKQuantityTypeIdentifierRunningVerticalOscillation: 'runningVerticalOscillation',
  // cycling biomechanics
  HKQuantityTypeIdentifierCyclingCadence: 'cyclingCadence',
  HKQuantityTypeIdentifierCyclingPower: 'cyclingPower',
  HKQuantityTypeIdentifierCyclingSpeed: 'cyclingSpeed',
  HKQuantityTypeIdentifierCyclingFunctionalThresholdPower: 'cyclingFTP',
  // swimming
  HKQuantityTypeIdentifierSwimmingStrokeCount: 'swimmingStrokeCount',
  // wheelchair
  HKQuantityTypeIdentifierPushCount: 'pushCount',
  // environment
  HKQuantityTypeIdentifierUVExposure: 'uvExposure',
  HKQuantityTypeIdentifierEnvironmentalAudioExposure: 'environmentalAudioExposure',
  HKQuantityTypeIdentifierHeadphoneAudioExposure: 'headphoneAudioExposure',
  // nutrition macros
  HKQuantityTypeIdentifierDietaryEnergyConsumed: 'dietaryEnergyConsumed',
  HKQuantityTypeIdentifierDietaryProtein: 'dietaryProtein',
  HKQuantityTypeIdentifierDietaryCarbohydrates: 'dietaryCarbohydrates',
  HKQuantityTypeIdentifierDietaryFatTotal: 'dietaryFatTotal',
  HKQuantityTypeIdentifierDietaryFatSaturated: 'dietaryFatSaturated',
  HKQuantityTypeIdentifierDietaryFatMonounsaturated: 'dietaryFatMonounsaturated',
  HKQuantityTypeIdentifierDietaryFatPolyunsaturated: 'dietaryFatPolyunsaturated',
  HKQuantityTypeIdentifierDietarySugar: 'dietarySugar',
  HKQuantityTypeIdentifierDietaryFiber: 'dietaryFiber',
  HKQuantityTypeIdentifierDietaryCholesterol: 'dietaryCholesterol',
  // nutrition hydration
  HKQuantityTypeIdentifierDietaryWater: 'dietaryWater',
  HKQuantityTypeIdentifierDietaryCaffeine: 'dietaryCaffeine',
  HKQuantityTypeIdentifierNumberOfAlcoholicBeverages: 'alcoholicBeverages',
  // nutrition electrolytes & minerals
  HKQuantityTypeIdentifierDietarySodium: 'dietarySodium',
  HKQuantityTypeIdentifierDietaryPotassium: 'dietaryPotassium',
  HKQuantityTypeIdentifierDietaryCalcium: 'dietaryCalcium',
  HKQuantityTypeIdentifierDietaryMagnesium: 'dietaryMagnesium',
  HKQuantityTypeIdentifierDietaryPhosphorus: 'dietaryPhosphorus',
  HKQuantityTypeIdentifierDietaryChloride: 'dietaryChloride',
  HKQuantityTypeIdentifierDietaryIron: 'dietaryIron',
  HKQuantityTypeIdentifierDietaryZinc: 'dietaryZinc',
  HKQuantityTypeIdentifierDietaryCopper: 'dietaryCopper',
  HKQuantityTypeIdentifierDietaryManganese: 'dietaryManganese',
  HKQuantityTypeIdentifierDietarySelenium: 'dietarySelenium',
  HKQuantityTypeIdentifierDietaryChromium: 'dietaryChromium',
  HKQuantityTypeIdentifierDietaryIodine: 'dietaryIodine',
  HKQuantityTypeIdentifierDietaryMolybdenum: 'dietaryMolybdenum',
  // nutrition vitamins
  HKQuantityTypeIdentifierDietaryVitaminA: 'dietaryVitaminA',
  HKQuantityTypeIdentifierDietaryVitaminB6: 'dietaryVitaminB6',
  HKQuantityTypeIdentifierDietaryVitaminB12: 'dietaryVitaminB12',
  HKQuantityTypeIdentifierDietaryVitaminC: 'dietaryVitaminC',
  HKQuantityTypeIdentifierDietaryVitaminD: 'dietaryVitaminD',
  HKQuantityTypeIdentifierDietaryVitaminE: 'dietaryVitaminE',
  HKQuantityTypeIdentifierDietaryVitaminK: 'dietaryVitaminK',
  HKQuantityTypeIdentifierDietaryBiotin: 'dietaryBiotin',
  HKQuantityTypeIdentifierDietaryFolate: 'dietaryFolate',
  HKQuantityTypeIdentifierDietaryNiacin: 'dietaryNiacin',
  HKQuantityTypeIdentifierDietaryRiboflavin: 'dietaryRiboflavin',
  HKQuantityTypeIdentifierDietaryThiamin: 'dietaryThiamin',
  HKQuantityTypeIdentifierDietaryPantothenicAcid: 'dietaryPantothenicAcid',
};

/** Unit string passed to queryQuantitySamples for each type */
const QUANTITY_UNITS: Record<(typeof HK_QUANTITY_TYPES)[number], string> = {
  // vitals
  HKQuantityTypeIdentifierHeartRate: 'count/min',
  HKQuantityTypeIdentifierRestingHeartRate: 'count/min',
  HKQuantityTypeIdentifierWalkingHeartRateAverage: 'count/min',
  HKQuantityTypeIdentifierHeartRateVariabilitySDNN: 'ms',
  HKQuantityTypeIdentifierOxygenSaturation: '%',
  HKQuantityTypeIdentifierRespiratoryRate: 'count/min',
  HKQuantityTypeIdentifierBodyTemperature: 'degC',
  HKQuantityTypeIdentifierAppleSleepingWristTemperature: 'degC',
  HKQuantityTypeIdentifierBloodPressureSystolic: 'mmHg',
  HKQuantityTypeIdentifierBloodPressureDiastolic: 'mmHg',
  HKQuantityTypeIdentifierBloodGlucose: 'mg/dL',
  HKQuantityTypeIdentifierVO2Max: 'mL/kg·min',
  HKQuantityTypeIdentifierAtrialFibrillationBurden: '%',
  // body
  HKQuantityTypeIdentifierBodyMass: 'kg',
  HKQuantityTypeIdentifierHeight: 'm',
  HKQuantityTypeIdentifierBodyMassIndex: 'count',
  HKQuantityTypeIdentifierBodyFatPercentage: '%',
  HKQuantityTypeIdentifierLeanBodyMass: 'kg',
  HKQuantityTypeIdentifierWaistCircumference: 'cm',
  // activity
  HKQuantityTypeIdentifierActiveEnergyBurned: 'kcal',
  HKQuantityTypeIdentifierBasalEnergyBurned: 'kcal',
  HKQuantityTypeIdentifierStepCount: 'count',
  HKQuantityTypeIdentifierFlightsClimbed: 'count',
  HKQuantityTypeIdentifierAppleExerciseTime: 'min',
  HKQuantityTypeIdentifierWorkoutEffortScore: 'appleEffortScore',
  HKQuantityTypeIdentifierPhysicalEffort: 'kcal/hr·kg',
  HKQuantityTypeIdentifierNumberOfTimesFallen: 'count',
  HKQuantityTypeIdentifierAppleWalkingSteadiness: '%',
  HKQuantityTypeIdentifierTimeInDaylight: 'min',
  // distances
  HKQuantityTypeIdentifierDistanceWalkingRunning: 'm',
  HKQuantityTypeIdentifierDistanceCycling: 'm',
  HKQuantityTypeIdentifierDistanceSwimming: 'm',
  HKQuantityTypeIdentifierDistanceCrossCountrySkiing: 'm',
  HKQuantityTypeIdentifierDistanceDownhillSnowSports: 'm',
  HKQuantityTypeIdentifierDistancePaddleSports: 'm',
  HKQuantityTypeIdentifierDistanceRowing: 'm',
  HKQuantityTypeIdentifierDistanceWheelchair: 'm',
  HKQuantityTypeIdentifierSixMinuteWalkTestDistance: 'm',
  // gait
  HKQuantityTypeIdentifierWalkingSpeed: 'm/s',
  HKQuantityTypeIdentifierWalkingStepLength: 'm',
  HKQuantityTypeIdentifierWalkingDoubleSupportPercentage: '%',
  HKQuantityTypeIdentifierWalkingAsymmetryPercentage: '%',
  HKQuantityTypeIdentifierStairAscentSpeed: 'ft/s',
  HKQuantityTypeIdentifierStairDescentSpeed: 'ft/s',
  // running biomechanics
  HKQuantityTypeIdentifierRunningSpeed: 'm/s',
  HKQuantityTypeIdentifierRunningPower: 'W',
  HKQuantityTypeIdentifierRunningGroundContactTime: 'ms',
  HKQuantityTypeIdentifierRunningStrideLength: 'm',
  HKQuantityTypeIdentifierRunningVerticalOscillation: 'cm',
  // cycling biomechanics
  HKQuantityTypeIdentifierCyclingCadence: 'count/min',
  HKQuantityTypeIdentifierCyclingPower: 'W',
  HKQuantityTypeIdentifierCyclingSpeed: 'm/s',
  HKQuantityTypeIdentifierCyclingFunctionalThresholdPower: 'W',
  // swimming
  HKQuantityTypeIdentifierSwimmingStrokeCount: 'count',
  // wheelchair
  HKQuantityTypeIdentifierPushCount: 'count',
  // environment
  HKQuantityTypeIdentifierUVExposure: 'count',
  HKQuantityTypeIdentifierEnvironmentalAudioExposure: 'dBASPL',
  HKQuantityTypeIdentifierHeadphoneAudioExposure: 'dBASPL',
  // nutrition macros
  HKQuantityTypeIdentifierDietaryEnergyConsumed: 'kcal',
  HKQuantityTypeIdentifierDietaryProtein: 'g',
  HKQuantityTypeIdentifierDietaryCarbohydrates: 'g',
  HKQuantityTypeIdentifierDietaryFatTotal: 'g',
  HKQuantityTypeIdentifierDietaryFatSaturated: 'g',
  HKQuantityTypeIdentifierDietaryFatMonounsaturated: 'g',
  HKQuantityTypeIdentifierDietaryFatPolyunsaturated: 'g',
  HKQuantityTypeIdentifierDietarySugar: 'g',
  HKQuantityTypeIdentifierDietaryFiber: 'g',
  HKQuantityTypeIdentifierDietaryCholesterol: 'mg',
  // nutrition hydration
  HKQuantityTypeIdentifierDietaryWater: 'mL',
  HKQuantityTypeIdentifierDietaryCaffeine: 'mg',
  HKQuantityTypeIdentifierNumberOfAlcoholicBeverages: 'count',
  // nutrition electrolytes & minerals
  HKQuantityTypeIdentifierDietarySodium: 'mg',
  HKQuantityTypeIdentifierDietaryPotassium: 'mg',
  HKQuantityTypeIdentifierDietaryCalcium: 'mg',
  HKQuantityTypeIdentifierDietaryMagnesium: 'mg',
  HKQuantityTypeIdentifierDietaryPhosphorus: 'mg',
  HKQuantityTypeIdentifierDietaryChloride: 'mg',
  HKQuantityTypeIdentifierDietaryIron: 'mg',
  HKQuantityTypeIdentifierDietaryZinc: 'mg',
  HKQuantityTypeIdentifierDietaryCopper: 'mg',
  HKQuantityTypeIdentifierDietaryManganese: 'mg',
  HKQuantityTypeIdentifierDietarySelenium: 'mcg',
  HKQuantityTypeIdentifierDietaryChromium: 'mcg',
  HKQuantityTypeIdentifierDietaryIodine: 'mcg',
  HKQuantityTypeIdentifierDietaryMolybdenum: 'mcg',
  // nutrition vitamins
  HKQuantityTypeIdentifierDietaryVitaminA: 'mcg',
  HKQuantityTypeIdentifierDietaryVitaminB6: 'mg',
  HKQuantityTypeIdentifierDietaryVitaminB12: 'mcg',
  HKQuantityTypeIdentifierDietaryVitaminC: 'mg',
  HKQuantityTypeIdentifierDietaryVitaminD: 'mcg',
  HKQuantityTypeIdentifierDietaryVitaminE: 'mg',
  HKQuantityTypeIdentifierDietaryVitaminK: 'mcg',
  HKQuantityTypeIdentifierDietaryBiotin: 'mcg',
  HKQuantityTypeIdentifierDietaryFolate: 'mcg',
  HKQuantityTypeIdentifierDietaryNiacin: 'mg',
  HKQuantityTypeIdentifierDietaryRiboflavin: 'mg',
  HKQuantityTypeIdentifierDietaryThiamin: 'mg',
  HKQuantityTypeIdentifierDietaryPantothenicAcid: 'mg',
};

/** Map HK category identifier → backend short name */
const CATEGORY_TYPE_MAP: Record<(typeof HK_CATEGORY_TYPES)[number], HealthKitReadType> = {
  HKCategoryTypeIdentifierSleepAnalysis: 'sleepAnalysis',
  HKCategoryTypeIdentifierMindfulSession: 'mindfulSession',
  HKCategoryTypeIdentifierAppleStandHour: 'appleStandHour',
  HKCategoryTypeIdentifierHighHeartRateEvent: 'highHeartRateEvent',
  HKCategoryTypeIdentifierLowHeartRateEvent: 'lowHeartRateEvent',
  HKCategoryTypeIdentifierIrregularHeartRhythmEvent: 'irregularHeartRhythmEvent',
  HKCategoryTypeIdentifierHeadache: 'headache',
  HKCategoryTypeIdentifierFatigue: 'fatigue',
  HKCategoryTypeIdentifierNausea: 'nausea',
  HKCategoryTypeIdentifierShortnessOfBreath: 'shortnessOfBreath',
  HKCategoryTypeIdentifierSleepChanges: 'sleepChanges',
};

// v14 API: `limit` is REQUIRED (use -1 for "all"), date filter lives under
// `filter.date.{startDate,endDate}`.
function makeOptions(from: Date, to: Date, unit?: string) {
  return {
    filter: { date: { startDate: from, endDate: to } },
    limit: -1,
    ascending: true,
    ...(unit ? { unit } : {}),
  };
}

async function readQuantitySamples(from: Date, to: Date): Promise<HealthSample[]> {
  const { queryQuantitySamples } = require('@kingstinct/react-native-healthkit') as {
    queryQuantitySamples: (
      identifier: string,
      options: ReturnType<typeof makeOptions>,
    ) => Promise<readonly HKQuantitySample[]>;
  };

  const all: HealthSample[] = [];
  for (const hkType of HK_QUANTITY_TYPES) {
    try {
      const unit = QUANTITY_UNITS[hkType];
      const samples = await queryQuantitySamples(hkType, makeOptions(from, to, unit));
      for (const s of samples) {
        all.push({
          type: QUANTITY_TYPE_MAP[hkType],
          start: toISO(s.startDate),
          end: toISO(s.endDate),
          value: toNumber(s.quantity),
          unit,
          source: sourceName(s),
        });
      }
    } catch (err) {
      console.warn(`[HealthKit] failed to read ${hkType}:`, err);
    }
  }
  return all;
}

async function readCategorySamples(from: Date, to: Date): Promise<HealthSample[]> {
  const { queryCategorySamples } = require('@kingstinct/react-native-healthkit') as {
    queryCategorySamples: (
      identifier: string,
      options: ReturnType<typeof makeOptions>,
    ) => Promise<readonly HKCategorySample[]>;
  };

  const all: HealthSample[] = [];
  for (const hkType of HK_CATEGORY_TYPES) {
    try {
      const samples = await queryCategorySamples(hkType, makeOptions(from, to));
      for (const s of samples) {
        all.push({
          type: CATEGORY_TYPE_MAP[hkType],
          start: toISO(s.startDate),
          end: toISO(s.endDate),
          value: toNumber(s.value),
          unit: 'category',
          source: sourceName(s),
        });
      }
    } catch (err) {
      console.warn(`[HealthKit] failed to read ${hkType}:`, err);
    }
  }
  return all;
}

// ---- workout reader ---------------------------------------------------------

type HKWorkoutSample = {
  startDate: Date | string;
  endDate: Date | string;
  workoutActivityType: number;
  duration?: number;
  totalEnergyBurned?: HKQuantityLike;
  sourceRevision?: { source?: { name?: string } };
};

function resolveWorkoutActivityTypeName(activityType: number): string {
  try {
    const { WorkoutActivityType } = require('@kingstinct/react-native-healthkit') as {
      WorkoutActivityType: Record<string, number>;
    };
    const key = Object.keys(WorkoutActivityType).find(
      (k) => WorkoutActivityType[k] === activityType && isNaN(Number(k)),
    );
    return key ?? 'workout';
  } catch {
    return 'workout';
  }
}

async function readWorkoutSamples(from: Date, to: Date): Promise<HealthSample[]> {
  const { queryWorkoutSamples } = require('@kingstinct/react-native-healthkit') as {
    queryWorkoutSamples: (
      options: ReturnType<typeof makeOptions>,
    ) => Promise<readonly HKWorkoutSample[]>;
  };

  try {
    const samples = await queryWorkoutSamples(makeOptions(from, to));
    return samples.map((s) => ({
      type: 'workout' as HealthKitReadType,
      start: toISO(s.startDate),
      end: toISO(s.endDate),
      value: toNumber(s.totalEnergyBurned),
      unit: 'kcal',
      source: s.sourceRevision?.source?.name ?? 'HealthKit',
      activityTypeName: resolveWorkoutActivityTypeName(s.workoutActivityType),
    }));
  } catch (err) {
    console.warn('[HealthKit] failed to read workouts:', err);
    return [];
  }
}

// ---- main export ------------------------------------------------------------

export async function runSync(
  opts: { force?: boolean } = {},
): Promise<{ uploaded: number; skipped?: boolean }> {
  if (!isHealthKitAvailable()) {
    console.log('[HealthKit] HealthKit unavailable — skipping sync.');
    return { uploaded: 0 };
  }

  const lastSyncRaw = await SecureStore.getItemAsync(LAST_SYNC_KEY);
  if (!opts.force && lastSyncRaw) {
    const ageMs = Date.now() - new Date(lastSyncRaw).getTime();
    if (ageMs < MIN_SYNC_INTERVAL_MS) {
      return { uploaded: 0, skipped: true };
    }
  }

  const sync = useSyncTimestamp.getState();
  sync.setSyncing(true);
  try {
    const from = lastSyncRaw ? new Date(lastSyncRaw) : daysAgo(LOOKBACK_DAYS);
    const to = new Date();

    const [quantitySamples, categorySamples, workoutSamples] = await Promise.all([
      readQuantitySamples(from, to),
      readCategorySamples(from, to),
      readWorkoutSamples(from, to),
    ]);

    const allSamples = [...quantitySamples, ...categorySamples, ...workoutSamples];
    if (allSamples.length === 0) {
      await SecureStore.setItemAsync(LAST_SYNC_KEY, to.toISOString());
      return { uploaded: 0 };
    }

    await persistDistinctSources(allSamples);

    let uploaded = 0;
    for (let i = 0; i < allSamples.length; i += CHUNK_SIZE) {
      const chunk = allSamples.slice(i, i + CHUNK_SIZE);
      await postChunk(chunk);
      uploaded += chunk.length;
    }

    await SecureStore.setItemAsync(LAST_SYNC_KEY, to.toISOString());
    return { uploaded };
  } finally {
    sync.markSynced();
  }
}
