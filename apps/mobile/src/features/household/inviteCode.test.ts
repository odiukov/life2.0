import { formatInviteInput } from './inviteCode';

it.each([
  ['abcd', 'ABCD'],
  ['abcde', 'ABCD-E'],
  ['abcd-ef12', 'ABCD-EF12'],
  ['ab cd ef 12 34', 'ABCD-EF12'],
  ['oIlL', '0111'],
  ['ABCD-EF1U', 'ABCD-EF1'],
])('formats %s as %s', (raw, expected) => {
  expect(formatInviteInput(raw)).toBe(expected);
});
