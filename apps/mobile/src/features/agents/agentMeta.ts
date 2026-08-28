// apps/mobile/src/features/agents/agentMeta.ts
import type { AgentId } from '@life-agents/ui';

export type QuickAction = {
  /** @deprecated kept temporarily for any callers reading it; new render path uses iconName. */
  emoji: string;
  /** Phosphor icon name (from phosphor-react-native). */
  iconName: string;
  label: string;
  subtitle: string;
  /** Sent immediately when tapped — navigates to Chat and fires this message. */
  message: string;
};

export type AgentMeta = {
  name: string;
  role: string;
  actions: readonly QuickAction[];
};

/** Accent color per agent — used for ring stroke, pill bg (10% opacity), primary action. */
export const AGENT_COLOR: Record<AgentId, string> = {
  sleep:      '#0ea5e9',
  workout:    '#10b981',
  nutrition:  '#f59e0b',
  mood:       '#ec4899',
  habits:     '#8b5cf6',
  recovery:   '#06b6d4',
  medication: '#f97316',
  finance:    '#22c55e',
  calendar:   '#64748b',
  home:       '#64748b',
  body:       '#a855f7',
};

export const AGENT_META: Record<AgentId, AgentMeta> = {
  sleep: {
    name: 'Sleep',
    role: 'Rest quality, HRV, and sleep stages',
    actions: [
      { emoji: '🔍', iconName: 'MagnifyingGlass', label: 'Analyze my sleep',      subtitle: 'Full breakdown + recommendations', message: 'Analyze my sleep from last night' },
      { emoji: '😴', iconName: 'Moon',            label: 'Improve deep sleep',    subtitle: 'Tips based on my patterns',        message: 'How can I improve my deep sleep?' },
      { emoji: '📊', iconName: 'ChartBar',        label: 'Sleep trend this week', subtitle: 'Compare with 7-day avg',           message: 'Show my sleep trend this week' },
      { emoji: '✏️', iconName: 'PencilSimple',    label: 'Log sleep manually',    subtitle: 'Add entry without HealthKit',      message: 'Log last night\'s sleep manually' },
    ],
  },
  workout: {
    name: 'Workout',
    role: 'Training load, recovery-aware recs',
    actions: [
      { emoji: '🏋️', iconName: 'Barbell',         label: 'Analyze my workout',      subtitle: 'Performance + recommendations', message: 'Analyze my workout performance' },
      { emoji: '➕', iconName: 'Plus',            label: 'Log a workout',           subtitle: 'Describe what I did',           message: 'Log a workout: ' },
      { emoji: '🎯', iconName: 'Target',          label: 'Training recommendation', subtitle: 'What should I do today?',       message: 'What workout should I do today?' },
      { emoji: '🔋', iconName: 'BatteryCharging', label: 'Recovery check',          subtitle: 'Safe to train hard?',           message: 'How is my recovery? Should I train hard today?' },
    ],
  },
  nutrition: {
    name: 'Nutrition',
    role: 'Meals, macros, daily intake',
    actions: [
      { emoji: '🥗', iconName: 'Leaf',      label: 'Analyze nutrition today', subtitle: 'Macro breakdown',                  message: 'Analyze my nutrition for today' },
      { emoji: '➕', iconName: 'Plus',      label: 'Log a meal',              subtitle: 'Describe what I ate',              message: 'Log a meal: ' },
      { emoji: '💡', iconName: 'Lightbulb', label: 'What should I eat?',      subtitle: 'Based on goals + today\'s intake', message: 'What should I eat for my next meal?' },
      { emoji: '📊', iconName: 'ChartBar',  label: 'Nutrition this week',     subtitle: '7-day macro trends',               message: 'Summarize my nutrition this week' },
    ],
  },
  mood: {
    name: 'Mood',
    role: 'Feeling, energy, stress',
    actions: [
      { emoji: '😊', iconName: 'Smiley',          label: 'Log my mood',        subtitle: 'Rate energy, stress, wellbeing', message: 'Log my mood' },
      { emoji: '🔍', iconName: 'MagnifyingGlass', label: 'Mood patterns',      subtitle: 'Trends + triggers',              message: 'Analyze my mood patterns this week' },
      { emoji: '😤', iconName: 'Wind',            label: 'Why am I stressed?', subtitle: 'Based on recent data',           message: 'Why might I be stressed based on my recent data?' },
      { emoji: '🧘', iconName: 'PersonSimple',    label: 'Coaching session',   subtitle: 'Guided check-in',                message: 'Start a mood coaching session' },
    ],
  },
  habits: {
    name: 'Habits',
    role: 'Daily check-ins and streaks',
    actions: [
      { emoji: '📊', iconName: 'ChartBar',        label: 'Streak summary',    subtitle: 'All habits + streak stats', message: 'Show my habit streak summary' },
      { emoji: '🔍', iconName: 'MagnifyingGlass', label: 'Analyze adherence', subtitle: 'Patterns + blockers',       message: 'Analyze my habit adherence patterns' },
      { emoji: '➕', iconName: 'Plus',            label: 'Create new habit',  subtitle: 'Describe it in chat',       message: 'Create a new habit: ' },
      { emoji: '🎯', iconName: 'Target',          label: 'Recommend a habit', subtitle: 'Based on my current data',  message: 'Recommend a new habit based on my health data' },
    ],
  },
  recovery: {
    name: 'Recovery',
    role: 'Readiness from HRV, RHR, stress',
    actions: [
      { emoji: '🔋', iconName: 'BatteryCharging', label: 'Recovery today',      subtitle: 'Readiness score',              message: 'How is my recovery today?' },
      { emoji: '🏃', iconName: 'PersonSimpleRun', label: 'Should I train?',     subtitle: 'Train or rest recommendation', message: 'Should I train hard or rest today?' },
      { emoji: '📈', iconName: 'TrendUp',         label: 'HRV trend this week', subtitle: '7-day variability',            message: 'Show my HRV trend this week' },
      { emoji: '💤', iconName: 'Bed',             label: 'Recovery tips',       subtitle: 'Based on current bucket',      message: 'Give me recovery tips based on my current state' },
    ],
  },
  medication: {
    name: 'Medication',
    role: 'Adherence and active list',
    actions: [
      { emoji: '💊', iconName: 'Pill',       label: 'Log medication taken', subtitle: 'Mark today\'s dose',    message: 'Log my medication taken' },
      { emoji: '📋', iconName: 'ListChecks', label: 'Active medications',   subtitle: 'Current schedule',      message: 'List my active medications' },
      { emoji: '⚠️', iconName: 'Warning',    label: 'What did I miss?',     subtitle: 'Adherence check',       message: 'What medications did I miss recently?' },
      { emoji: '📊', iconName: 'ChartBar',   label: 'Adherence analysis',   subtitle: 'Patterns over 14 days', message: 'Analyze my medication adherence over the last 14 days' },
    ],
  },
  finance: {
    name: 'Finance',
    role: 'Income, spending, runway',
    actions: [
      { emoji: '💰', iconName: 'CurrencyDollar', label: 'Monthly summary',      subtitle: 'Income, spending, balance', message: 'Give me a finance summary for this month' },
      { emoji: '📂', iconName: 'FolderOpen',     label: 'Spending by category', subtitle: 'Where the money went',      message: 'Break down my spending by category this month' },
      { emoji: '🛣️', iconName: 'PathIcon',       label: 'Runway',               subtitle: 'Months at current spend',   message: 'What is my financial runway at current spend?' },
      { emoji: '📄', iconName: 'FileArrowUp',    label: 'Upload statement',     subtitle: 'Attach Payoneer PDF',       message: 'I want to upload a finance statement' },
    ],
  },
  calendar: {
    name: 'Calendar',
    role: 'Meetings and free slots',
    actions: [
      { emoji: '📅', iconName: 'Calendar',     label: "Today's schedule", subtitle: 'All meetings',        message: "What is on my calendar today?" },
      { emoji: '🕐', iconName: 'Clock',        label: 'Next free slot',   subtitle: 'First open hour',     message: 'When is my next free hour?' },
      { emoji: '📆', iconName: 'CalendarPlus', label: 'Tomorrow',         subtitle: "Tomorrow's agenda",   message: "What's on my calendar tomorrow?" },
      { emoji: '➕', iconName: 'Plus',         label: 'Create event',     subtitle: 'Describe it in chat', message: 'Create a calendar event: ' },
    ],
  },
  home: {
    name: 'Home',
    role: 'Home Assistant state & scenes',
    actions: [
      { emoji: '🏠', iconName: 'House',       label: 'House state',     subtitle: 'Current sensor readings',  message: 'What is the current state of the house?' },
      { emoji: '🌡️', iconName: 'Thermometer', label: 'Bedroom climate', subtitle: 'Temperature and humidity', message: 'What is the bedroom temperature and humidity?' },
      { emoji: '🤖', iconName: 'Robot',       label: 'Start cleaning',  subtitle: 'Vacuum the floors',        message: 'Start the vacuum cleaner' },
      { emoji: '💡', iconName: 'Lightbulb',   label: 'Control lights',  subtitle: 'Adjust lighting',          message: 'Control the lights: ' },
    ],
  },
  body: {
    name: 'Body',
    role: 'Weight, body composition, BMI',
    actions: [
      { emoji: '⚖️', iconName: 'Scales',          label: 'Log weight',       subtitle: 'Record today\'s weight',  message: 'Log my weight' },
      { emoji: '📊', iconName: 'ChartBar',        label: 'Weight trend',     subtitle: '30-day bodyweight chart', message: 'Show my weight trend for the last 30 days' },
      { emoji: '🔍', iconName: 'MagnifyingGlass', label: 'Body composition', subtitle: 'BMI, fat %, muscle mass', message: 'Analyze my body composition' },
      { emoji: '🎯', iconName: 'Target',          label: 'Goal progress',    subtitle: 'How far to my target',    message: 'How am I progressing toward my body goal?' },
    ],
  },
};
