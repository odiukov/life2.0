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
