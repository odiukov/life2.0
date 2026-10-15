import { apiBaseUrl, apiMode } from './client';
test('defaults to the mock gateway origin', () => {
  expect(apiMode).toBe('mock');
  expect(apiBaseUrl).toBe('http://mock.local');
});
