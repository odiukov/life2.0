export type AppLocale = 'ru' | 'en';

/** Use Russian for Russian device locales and English for all others. */
export function appLocale(): AppLocale {
  const device = Intl.DateTimeFormat().resolvedOptions().locale ?? 'en';
  return device.toLowerCase().startsWith('ru') ? 'ru' : 'en';
}
