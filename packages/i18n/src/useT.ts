import { useCallback, useMemo } from 'react';
import { en } from './strings/en';
import { ru } from './strings/ru';

type Locale = 'en' | 'ru';

const bundles = { en, ru } as const;

export function useT(locale: Locale = 'en') {
  const bundle = useMemo(() => bundles[locale], [locale]);
  return useCallback(
    (key: string) => {
      const parts = key.split('.');
      let cur: unknown = bundle;
      for (const p of parts) {
        cur = (cur as Record<string, unknown>)?.[p];
        if (cur == null) return key;
      }
      return typeof cur === 'string' ? cur : key;
    },
    [bundle],
  );
}
