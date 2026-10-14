import { badgeText } from './badge';

it.each([[0, null], [1, '1'], [99, '99'], [100, '99+']])('%d → %p', (count, text) => {
  expect(badgeText(count)).toBe(text);
});
