import type { AgentId } from '@life-agents/ui';

export type QuickAction = {
  label: string;
  subtitle: string;
  message: string;
};

export const QUICK_ACTIONS: Record<AgentId, QuickAction[]> = {
  sleep: [
    { label: 'Log a nap', subtitle: 'Duration, quality, notes', message: '/sleep log a nap — 25 min, refreshed' },
    { label: "Tonight's plan", subtitle: 'Ideal bedtime + wind-down', message: '/sleep recommend bedtime for tonight' },
    { label: 'Weekly review', subtitle: '7-day trends + outliers', message: '/sleep weekly summary' },
  ],
  workout: [
    { label: 'What should I do today?', subtitle: 'Based on readiness + load', message: '/workout suggest today' },
    { label: 'Log a workout', subtitle: 'Add a session manually', message: '/workout log session' },
    { label: 'Training load', subtitle: 'Past 4 weeks by zone', message: '/workout load last 28d' },
  ],
  nutrition: [
    { label: 'Log what I ate', subtitle: 'Photo, voice or text', message: '/nutrition log lunch' },
    { label: 'Plan dinner', subtitle: 'Fit remaining macros', message: '/nutrition plan dinner' },
    { label: 'Review the week', subtitle: 'Adherence + deficits', message: '/nutrition weekly review' },
  ],
  mood: [
    { label: 'Quick check-in', subtitle: 'Mood · energy · stress', message: '/mood quick check-in' },
    { label: 'Journal entry', subtitle: 'Free-form, private', message: '/journal' },
    { label: 'Patterns', subtitle: 'What drives your mood', message: '/mood patterns last 30d' },
  ],
  habits: [
    { label: "Today's check-ins", subtitle: '5 habits · 3 done', message: '/habits today' },
    { label: 'Add a habit', subtitle: 'Name, cue, cadence', message: '/habit add' },
    { label: '30-day streaks', subtitle: 'See what stuck', message: '/habits streaks' },
  ],
  medication: [
    { label: 'Mark dose taken', subtitle: 'Magnesium 400mg · due 20:00', message: '/med took magnesium 400mg' },
    { label: 'Adherence this week', subtitle: 'Missed doses + patterns', message: '/med adherence 7d' },
    { label: 'Add a medication', subtitle: 'Name, dose, schedule', message: '/med add' },
  ],
  recovery: [
    { label: "Today's readiness", subtitle: '82 · green', message: '/recovery today' },
    { label: 'Why this score?', subtitle: 'Breakdown + drivers', message: '/recovery explain' },
    { label: 'Ramp suggestion', subtitle: 'How hard can I train?', message: '/recovery what should I do' },
  ],
  calendar: [
    { label: "Today's meetings", subtitle: '4 events · 3h 15m', message: '/calendar today' },
    { label: 'Find me 30 min', subtitle: 'For focused work', message: '/calendar find focus block' },
    { label: 'Weekly load', subtitle: 'Meeting density', message: '/calendar load this week' },
  ],
  finance: [
    { label: 'This month', subtitle: 'By category · vs last', message: '/finance month' },
    { label: 'Top merchants', subtitle: 'Where money actually goes', message: '/finance merchants' },
    { label: 'Subscriptions audit', subtitle: 'Cancel candidates', message: '/finance subscriptions' },
  ],
  home: [
    { label: "Set scene 'Focus'", subtitle: 'Desk lamp · DND · 21°C', message: '/ha scene focus' },
    { label: 'State snapshot', subtitle: 'Everything in one view', message: '/ha state' },
    { label: 'Motion events', subtitle: 'Last 24 hours', message: '/ha motion last 24h' },
  ],
  body: [
    { label: 'Log weight', subtitle: "Today's reading", message: '/body log weight' },
    { label: 'Body composition', subtitle: 'Fat % trend', message: '/body composition' },
    { label: 'Progress photo', subtitle: 'Add to timeline', message: '/body photo' },
  ],
};
