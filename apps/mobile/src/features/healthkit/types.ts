// HK quantity-type identifiers (full HK identifier format required by
// @kingstinct/react-native-healthkit). Grouped by category for readability.
export const HK_QUANTITY_TYPES = [
  // --- Vitals & cardio ---
  'HKQuantityTypeIdentifierHeartRate',
  'HKQuantityTypeIdentifierRestingHeartRate',
  'HKQuantityTypeIdentifierWalkingHeartRateAverage',
  'HKQuantityTypeIdentifierHeartRateVariabilitySDNN',
  'HKQuantityTypeIdentifierOxygenSaturation',
  'HKQuantityTypeIdentifierRespiratoryRate',
  'HKQuantityTypeIdentifierBodyTemperature',
  'HKQuantityTypeIdentifierAppleSleepingWristTemperature',
  'HKQuantityTypeIdentifierBloodPressureSystolic',
  'HKQuantityTypeIdentifierBloodPressureDiastolic',
  'HKQuantityTypeIdentifierBloodGlucose',
  'HKQuantityTypeIdentifierVO2Max',
  'HKQuantityTypeIdentifierAtrialFibrillationBurden',

  // --- Body measurements ---
  'HKQuantityTypeIdentifierBodyMass',
  'HKQuantityTypeIdentifierHeight',
  'HKQuantityTypeIdentifierBodyMassIndex',
  'HKQuantityTypeIdentifierBodyFatPercentage',
  'HKQuantityTypeIdentifierLeanBodyMass',
  'HKQuantityTypeIdentifierWaistCircumference',

  // --- Activity & energy ---
  'HKQuantityTypeIdentifierActiveEnergyBurned',
  'HKQuantityTypeIdentifierBasalEnergyBurned',
  'HKQuantityTypeIdentifierStepCount',
  'HKQuantityTypeIdentifierFlightsClimbed',
  'HKQuantityTypeIdentifierAppleExerciseTime',
  'HKQuantityTypeIdentifierWorkoutEffortScore',
  'HKQuantityTypeIdentifierPhysicalEffort',
  'HKQuantityTypeIdentifierNumberOfTimesFallen',
  'HKQuantityTypeIdentifierAppleWalkingSteadiness',
  'HKQuantityTypeIdentifierTimeInDaylight',

  // --- Distances ---
  'HKQuantityTypeIdentifierDistanceWalkingRunning',
  'HKQuantityTypeIdentifierDistanceCycling',
  'HKQuantityTypeIdentifierDistanceSwimming',
  'HKQuantityTypeIdentifierDistanceCrossCountrySkiing',
  'HKQuantityTypeIdentifierDistanceDownhillSnowSports',
  'HKQuantityTypeIdentifierDistancePaddleSports',
  'HKQuantityTypeIdentifierDistanceRowing',
  'HKQuantityTypeIdentifierDistanceWheelchair',
  'HKQuantityTypeIdentifierSixMinuteWalkTestDistance',

  // --- Gait & mobility ---
  'HKQuantityTypeIdentifierWalkingSpeed',
  'HKQuantityTypeIdentifierWalkingStepLength',
  'HKQuantityTypeIdentifierWalkingDoubleSupportPercentage',
  'HKQuantityTypeIdentifierWalkingAsymmetryPercentage',
  'HKQuantityTypeIdentifierStairAscentSpeed',
  'HKQuantityTypeIdentifierStairDescentSpeed',

  // --- Running biomechanics (iOS 16+) ---
  'HKQuantityTypeIdentifierRunningSpeed',
  'HKQuantityTypeIdentifierRunningPower',
  'HKQuantityTypeIdentifierRunningGroundContactTime',
  'HKQuantityTypeIdentifierRunningStrideLength',
  'HKQuantityTypeIdentifierRunningVerticalOscillation',

  // --- Cycling biomechanics (iOS 17+) ---
  'HKQuantityTypeIdentifierCyclingCadence',
  'HKQuantityTypeIdentifierCyclingPower',
  'HKQuantityTypeIdentifierCyclingSpeed',
  'HKQuantityTypeIdentifierCyclingFunctionalThresholdPower',

  // --- Swimming ---
  'HKQuantityTypeIdentifierSwimmingStrokeCount',

  // --- Wheelchair ---
  'HKQuantityTypeIdentifierPushCount',

  // --- Environment ---
  'HKQuantityTypeIdentifierUVExposure',
  'HKQuantityTypeIdentifierEnvironmentalAudioExposure',
  'HKQuantityTypeIdentifierHeadphoneAudioExposure',

  // --- Nutrition: macros & energy ---
  'HKQuantityTypeIdentifierDietaryEnergyConsumed',
  'HKQuantityTypeIdentifierDietaryProtein',
  'HKQuantityTypeIdentifierDietaryCarbohydrates',
  'HKQuantityTypeIdentifierDietaryFatTotal',
  'HKQuantityTypeIdentifierDietaryFatSaturated',
  'HKQuantityTypeIdentifierDietaryFatMonounsaturated',
  'HKQuantityTypeIdentifierDietaryFatPolyunsaturated',
  'HKQuantityTypeIdentifierDietarySugar',
  'HKQuantityTypeIdentifierDietaryFiber',
  'HKQuantityTypeIdentifierDietaryCholesterol',

  // --- Nutrition: hydration & other ---
  'HKQuantityTypeIdentifierDietaryWater',
  'HKQuantityTypeIdentifierDietaryCaffeine',
  'HKQuantityTypeIdentifierNumberOfAlcoholicBeverages',

  // --- Nutrition: electrolytes & minerals ---
  'HKQuantityTypeIdentifierDietarySodium',
  'HKQuantityTypeIdentifierDietaryPotassium',
  'HKQuantityTypeIdentifierDietaryCalcium',
  'HKQuantityTypeIdentifierDietaryMagnesium',
  'HKQuantityTypeIdentifierDietaryPhosphorus',
  'HKQuantityTypeIdentifierDietaryChloride',
  'HKQuantityTypeIdentifierDietaryIron',
  'HKQuantityTypeIdentifierDietaryZinc',
  'HKQuantityTypeIdentifierDietaryCopper',
  'HKQuantityTypeIdentifierDietaryManganese',
  'HKQuantityTypeIdentifierDietarySelenium',
  'HKQuantityTypeIdentifierDietaryChromium',
  'HKQuantityTypeIdentifierDietaryIodine',
  'HKQuantityTypeIdentifierDietaryMolybdenum',

  // --- Nutrition: vitamins ---
  'HKQuantityTypeIdentifierDietaryVitaminA',
  'HKQuantityTypeIdentifierDietaryVitaminB6',
  'HKQuantityTypeIdentifierDietaryVitaminB12',
  'HKQuantityTypeIdentifierDietaryVitaminC',
  'HKQuantityTypeIdentifierDietaryVitaminD',
  'HKQuantityTypeIdentifierDietaryVitaminE',
  'HKQuantityTypeIdentifierDietaryVitaminK',
  'HKQuantityTypeIdentifierDietaryBiotin',
  'HKQuantityTypeIdentifierDietaryFolate',
  'HKQuantityTypeIdentifierDietaryNiacin',
  'HKQuantityTypeIdentifierDietaryRiboflavin',
  'HKQuantityTypeIdentifierDietaryThiamin',
  'HKQuantityTypeIdentifierDietaryPantothenicAcid',
] as const;

// Category types — sleep, mindfulness, cardiac events, symptoms
export const HK_CATEGORY_TYPES = [
  'HKCategoryTypeIdentifierSleepAnalysis',
  'HKCategoryTypeIdentifierMindfulSession',
  'HKCategoryTypeIdentifierAppleStandHour',
  // cardiac events
  'HKCategoryTypeIdentifierHighHeartRateEvent',
  'HKCategoryTypeIdentifierLowHeartRateEvent',
  'HKCategoryTypeIdentifierIrregularHeartRhythmEvent',
  // symptoms
  'HKCategoryTypeIdentifierHeadache',
  'HKCategoryTypeIdentifierFatigue',
  'HKCategoryTypeIdentifierNausea',
  'HKCategoryTypeIdentifierShortnessOfBreath',
  'HKCategoryTypeIdentifierSleepChanges',
] as const;

// Workout type — separate HealthKit authorization category
export const HK_WORKOUT_TYPE = 'HKWorkoutTypeIdentifier' as const;

// Friendly short-names used by the backend /sync/health endpoint.
export const HEALTHKIT_READ_TYPES = [
  // sleep / mindfulness
  'sleepAnalysis',
  'mindfulSession',
  'appleStandHour',
  // workout
  'workout',
  // cardio vitals
  'heartRate',
  'restingHeartRate',
  'walkingHeartRateAverage',
  'heartRateVariabilitySDNN',
  'oxygenSaturation',
  'respiratoryRate',
  'bodyTemperature',
  'sleepingWristTemperature',
  'bloodPressureSystolic',
  'bloodPressureDiastolic',
  'bloodGlucose',
  'vo2Max',
  'atrialFibrillationBurden',
  // body
  'bodyMass',
  'height',
  'bodyMassIndex',
  'bodyFatPercentage',
  'leanBodyMass',
  'waistCircumference',
  // activity
  'activeEnergyBurned',
  'basalEnergyBurned',
  'stepCount',
  'flightsClimbed',
  'exerciseTime',
  'workoutEffortScore',
  'physicalEffort',
  'timesFallen',
  'walkingSteadiness',
  'timeInDaylight',
  // distances
  'distanceWalkingRunning',
  'distanceCycling',
  'distanceSwimming',
  'distanceCrossCountrySkiing',
  'distanceDownhillSnowSports',
  'distancePaddleSports',
  'distanceRowingSports',
  'distanceWheelchair',
  'sixMinuteWalkTestDistance',
  // gait & mobility
  'walkingSpeed',
  'walkingStepLength',
  'walkingDoubleSupportPercentage',
  'walkingAsymmetryPercentage',
  'stairAscentSpeed',
  'stairDescentSpeed',
  // running biomechanics
  'runningSpeed',
  'runningPower',
  'runningGroundContactTime',
  'runningStrideLength',
  'runningVerticalOscillation',
  // cycling biomechanics
  'cyclingCadence',
  'cyclingPower',
  'cyclingSpeed',
  'cyclingFTP',
  // swimming
  'swimmingStrokeCount',
  // wheelchair
  'pushCount',
  // environment
  'uvExposure',
  'environmentalAudioExposure',
  'headphoneAudioExposure',
  // cardiac events (category)
  'highHeartRateEvent',
  'lowHeartRateEvent',
  'irregularHeartRhythmEvent',
  // symptoms (category)
  'headache',
  'fatigue',
  'nausea',
  'shortnessOfBreath',
  'sleepChanges',
  // nutrition macros
  'dietaryEnergyConsumed',
  'dietaryProtein',
  'dietaryCarbohydrates',
  'dietaryFatTotal',
  'dietaryFatSaturated',
  'dietaryFatMonounsaturated',
  'dietaryFatPolyunsaturated',
  'dietarySugar',
  'dietaryFiber',
  'dietaryCholesterol',
  // nutrition hydration
  'dietaryWater',
  'dietaryAlcohol',
  'dietaryCaffeine',
  'alcoholicBeverages',
  // nutrition electrolytes
  'dietarySodium',
  'dietaryPotassium',
  'dietaryCalcium',
  'dietaryMagnesium',
  'dietaryPhosphorus',
  'dietaryChloride',
  'dietaryIron',
  'dietaryZinc',
  'dietaryCopper',
  'dietaryManganese',
  'dietarySelenium',
  'dietaryChromium',
  'dietaryIodine',
  'dietaryMolybdenum',
  // nutrition vitamins
  'dietaryVitaminA',
  'dietaryVitaminB6',
  'dietaryVitaminB12',
  'dietaryVitaminC',
  'dietaryVitaminD',
  'dietaryVitaminE',
  'dietaryVitaminK',
  'dietaryBiotin',
  'dietaryFolate',
  'dietaryNiacin',
  'dietaryRiboflavin',
  'dietaryThiamin',
  'dietaryPantothenicAcid',
] as const;

export type HealthKitReadType = (typeof HEALTHKIT_READ_TYPES)[number];

/** Shape of a single sample sent to POST /sync/health */
export interface HealthSample {
  type: HealthKitReadType;
  start: string; // ISO-8601
  end: string;   // ISO-8601
  value: number;
  unit: string;
  source: string;
  activityTypeName?: string; // workout samples only — camelCase HKWorkoutActivityType key
}
