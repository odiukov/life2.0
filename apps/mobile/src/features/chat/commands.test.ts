import { matchCommands } from './commands';

test('empty string matches nothing', () => {
  expect(matchCommands('')).toHaveLength(0);
});

test('"/finance" is hidden when payoneer not connected', () => {
  const m = matchCommands('/fin');
  expect(m).toHaveLength(0);
});

test('"/finance" appears when payoneer connected', () => {
  const m = matchCommands('/fin', new Set(['payoneer']));
  expect(m.map((c) => c.name)).toContain('/finance');
});

test('"/ha" command hidden by default (only /habit and /habits match)', () => {
  const names = matchCommands('/ha').map((c) => c.name);
  expect(names).not.toContain('/ha');
  expect(names).toContain('/habit');
  expect(names).toContain('/habits');
});

test('"/ha" shows when ha connected', () => {
  const names = matchCommands('/ha', new Set(['ha'])).map((c) => c.name);
  expect(names).toContain('/ha');
  // also 'habit' and 'habits' start with /ha too, so we expect 3 entries
  expect(matchCommands('/ha', new Set(['ha']))).toHaveLength(3);
});

test('"/" returns all base + connected gated commands', () => {
  const base = matchCommands('/');
  const withPayoneer = matchCommands('/', new Set(['payoneer']));
  expect(withPayoneer.length).toBe(base.length + 1);
});

test('non-slash text matches nothing', () => {
  expect(matchCommands('hello', new Set(['payoneer']))).toHaveLength(0);
});
