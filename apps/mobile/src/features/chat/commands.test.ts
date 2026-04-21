import { matchCommands } from './commands';

test('empty string matches nothing', () => {
  expect(matchCommands('')).toHaveLength(0);
});

test('non-slash text matches nothing', () => {
  expect(matchCommands('hello world')).toHaveLength(0);
});

test('just "/" matches all commands', () => {
  expect(matchCommands('/').length).toBeGreaterThan(5);
});

test('"/sl" matches /sleep', () => {
  const m = matchCommands('/sl');
  expect(m).toHaveLength(1);
  expect(m[0]?.name).toBe('/sleep');
});

test('"/h" matches habit commands', () => {
  const names = matchCommands('/h').map((c) => c.name);
  expect(names).toContain('/habit');
  expect(names).toContain('/habits');
});
