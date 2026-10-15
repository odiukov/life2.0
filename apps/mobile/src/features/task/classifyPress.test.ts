import { CANCEL_DX, classifyPress, isCancelArmed } from './classifyPress';

test.each([
  [{ held: false, dx: 0 }, 'tap'],
  [{ held: false, dx: -200 }, 'tap'],
  [{ held: true, dx: 0 }, 'send'],
  [{ held: true, dx: 40 }, 'send'],
  [{ held: true, dx: CANCEL_DX }, 'send'],
  [{ held: true, dx: CANCEL_DX - 1 }, 'cancel'],
] as const)('%o → %s', (input, expected) => {
  expect(classifyPress(input)).toBe(expected);
});

test('cancel arms only past the threshold', () => {
  expect(isCancelArmed(-80)).toBe(false);
  expect(isCancelArmed(-81)).toBe(true);
});
