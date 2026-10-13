import { renderHook } from '@testing-library/react-native';
import { useT } from './useT';

test('returns the RU string for a known key', () => {
  const { result } = renderHook(() => useT('ru'));
  expect(result.current('tabs.today')).toBe('Сегодня');
});

test('returns the key when not found', () => {
  const { result } = renderHook(() => useT('ru'));
  expect(result.current('nonexistent.key')).toBe('nonexistent.key');
});

test('falls back to EN bundle when key missing in RU', () => {
  const { result } = renderHook(() => useT('ru'));
  // _test.enOnly exists in en.json only — RU lookup must fall back to EN.
  expect(result.current('_test.enOnly')).toBe('Englishfallback');
});

test('returns localized string when key exists in both bundles', () => {
  const { result } = renderHook(() => useT('ru'));
  expect(result.current('states.loading')).toBe('Загрузка…');
});

test('interpolates named params', () => {
  const { result } = renderHook(() => useT('en'));
  expect(result.current('_test.greeting', { name: 'world' })).toBe('Hi world');
});

describe('CLDR plural lookup', () => {
  const en = require('../locales/en.json') as Record<string, unknown>;
  const ru = require('../locales/ru.json') as Record<string, unknown>;

  beforeAll(() => {
    en._pluralTest = {
      items: { one: '{count} item', other: '{count} items' },
      onlyEn: { one: '{count} fallback item', other: '{count} fallback items' },
      otherOnly: { other: '{count} generic items' },
      invalid: { label: 'not a plural entry' },
    };
    ru._pluralTest = {
      items: {
        one: '{count} продукт',
        few: '{count} продукта',
        many: '{count} продуктов',
        other: '{count} продукта',
      },
    };
  });

  afterAll(() => {
    delete en._pluralTest;
    delete ru._pluralTest;
  });

  test.each([
    [0, '0 продуктов'],
    [1, '1 продукт'],
    [3, '3 продукта'],
    [5, '5 продуктов'],
    [11, '11 продуктов'],
    [21, '21 продукт'],
    [22, '22 продукта'],
    [1.5, '1.5 продукта'],
  ])('selects Russian category for %s', (count, expected) => {
    const { result } = renderHook(() => useT('ru'));
    expect(result.current('_pluralTest.items', { count })).toBe(expected);
  });

  test.each([
    [0, '0 items'],
    [1, '1 item'],
    [2, '2 items'],
    [21, '21 items'],
  ])('selects English category for %s', (count, expected) => {
    const { result } = renderHook(() => useT('en'));
    expect(result.current('_pluralTest.items', { count })).toBe(expected);
  });

  test('uses English plural rules when the requested entry is absent', () => {
    const { result } = renderHook(() => useT('ru'));
    expect(result.current('_pluralTest.onlyEn', { count: 21 })).toBe('21 fallback items');
    expect(result.current('_pluralTest.onlyEn', { count: 1 })).toBe('1 fallback item');
  });

  test('uses other if selected category is absent', () => {
    const { result } = renderHook(() => useT('en'));
    expect(result.current('_pluralTest.otherOnly', { count: 1 })).toBe('1 generic items');
  });

  test('returns key for ordinary object and interpolates after default plural selection', () => {
    const { result } = renderHook(() => useT('en'));
    expect(result.current('_pluralTest.invalid', { count: 1 })).toBe('_pluralTest.invalid');
    expect(result.current('_pluralTest.items')).toBe('{count} item');
  });
});
