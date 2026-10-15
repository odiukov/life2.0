import { BASE_LEADS, quickLeads } from './quickChips';

test('calendar and home only when connected', () => {
  expect(quickLeads(new Set())).toEqual(BASE_LEADS);
  expect(quickLeads(new Set(['calendar', 'ha'] as never))).toEqual([
    ...BASE_LEADS,
    'calendar',
    'home',
  ]);
});
