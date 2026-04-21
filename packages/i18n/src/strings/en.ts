export const en = {
  onboarding: {
    welcomeHero: 'Your health, your money, your days — one conversation.',
    getStarted: 'Get started',
    signInApple: 'Continue with Apple',
    signInGoogle: 'Continue with Google',
    signInEmail: 'Continue with email',
    toneTitle: 'Pick a voice',
    toneSubtitle: 'Change anytime in Settings.',
    permissionsHealth: 'Connect Apple Health',
    permissionsNotif: 'Enable notifications',
    firstChatStart: 'Start chatting',
  },
  tabs: { chat: 'Chat', today: 'Today', dash: 'Dash', more: 'More' },
  more: {
    integrations: 'Integrations',
    tone: 'Voice & tone',
    privacy: 'Privacy & data',
    subscription: 'Subscription',
    about: 'About',
  },
  states: {
    loading: 'Loading…',
    errorLoadToday: "Couldn't load today",
    errorLoadDashboard: "Couldn't load dashboard",
    retry: 'Retry',
  },
} as const;

// Structural type with string values — lets other locales satisfy the shape
// without being locked to EN literal strings.
type Widen<T> = T extends string
  ? string
  : { [K in keyof T]: Widen<T[K]> };

export type Strings = Widen<typeof en>;
