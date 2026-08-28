import type { AgentId } from '@life-agents/ui';

/**
 * Short user-facing label and description for each agent shown in the
 * chat-header bottom sheet. Description is the one-line subtitle
 * displayed under the agent name. The canonical iteration order is
 * `AGENT_DISPLAY_ORDER` in `agentStatusRules.ts` — do not rely on the
 * key order here.
 */
export const AGENT_COPY = {
  sleep: { label: 'Sleep', description: 'Tracks bedtime, duration, HRV' },
  workout: { label: 'Training', description: 'Workouts, load, recovery' },
  nutrition: { label: 'Nutrition', description: 'Calories, macros, meals' },
  recovery: { label: 'Recovery', description: 'Readiness, HRV trend, fatigue' },
  body: { label: 'Body', description: 'Weight, height, body composition' },
  mood: { label: 'Mood', description: 'Daily mood, energy, sentiment' },
  habits: { label: 'Habits', description: 'Routines, streaks, daily wins' },
  medication: { label: 'Medication', description: 'Doses, schedule, reminders' },
  calendar: { label: 'Calendar', description: 'Meetings, events, schedule' },
  home: { label: 'Home', description: 'Smart-home automation & device state' },
  finance: { label: 'Finance', description: 'Spending, income, budgets' },
} as const satisfies Record<AgentId, { label: string; description: string }>;

/**
 * Hint strings shown when an agent is not ready. Lookup keys are
 * defined in agentStatusRules.ts; values are plain English copy.
 */
export const HINT_COPY = {
  sleep_no_source: 'Connect Apple Health or Garmin to track sleep',
  workout_no_source: 'Connect a fitness source (Apple Health, Garmin or Strava)',
  nutrition_no_source: 'Connect Yazio or log a meal in chat',
  recovery_no_source: 'Connect Garmin or Apple Health for HRV',
  body_no_data: 'Tell me your weight and height in chat',
  mood_no_data: 'Log your first mood — how do you feel?',
  habits_no_data: 'Add your first habit in chat',
  medication_no_data: 'Tell me what meds you take',
  home_no_token: 'Add Home Assistant token in Settings',
  calendar_not_connected: 'Connect Google Calendar',
  finance_no_data: 'Upload finance CSV or connect Payoneer',
  /** Fallback used by any agent whose source is connected but has no recent metric. */
  no_recent_data: 'No recent data — pull to refresh on Home',
} as const;

export type HintKey = keyof typeof HINT_COPY;
