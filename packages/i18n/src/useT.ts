import { useCallback, useMemo } from 'react';
import enJson from '../locales/en.json';
import ruJson from '../locales/ru.json';

type Locale = 'en' | 'ru';

const bundles = {
  en: enJson as Record<string, unknown>,
  ru: ruJson as Record<string, unknown>,
} as const;

function lookup(bundle: Record<string, unknown>, key: string): string | null {
  let cur: unknown = bundle;
  for (const part of key.split('.')) {
    if (cur == null || typeof cur !== 'object') return null;
    cur = (cur as Record<string, unknown>)[part];
  }
  return typeof cur === 'string' ? cur : null;
}

/**
 * Localized string accessor with optional `{name}` parameter interpolation.
 *
 * Lookup order: requested locale → EN fallback → key string verbatim.
 * Interpolation: `t('greeting', { name: 'X' })` substitutes `{name}` → 'X'.
 * Param values are inserted as plain text — they are NOT escaped against
 * containing `{otherKey}` sequences. Callers must sanitize user-controlled input
 * if more than one param key is present.
 */
export function useT(locale: Locale = 'en') {
  const bundle = useMemo(() => bundles[locale], [locale]);
  const en = bundles.en;
  return useCallback(
    (key: string, params?: Record<string, string | number>) => {
      let str = lookup(bundle, key) ?? lookup(en, key) ?? key;
      if (params) {
        for (const k of Object.keys(params)) {
          str = str.split(`{${k}}`).join(String(params[k]));
        }
      }
      return str;
    },
    [bundle, en],
  );
}
