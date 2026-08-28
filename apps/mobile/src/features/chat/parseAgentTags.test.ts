import { parseAgentTags } from './parseAgentTags';

test('plain text returns one string segment', () => {
  expect(parseAgentTags('hello world')).toEqual(['hello world']);
});

test('leading agent tag becomes a tag segment', () => {
  expect(parseAgentTags('/sleep как я спал?')).toEqual([
    { tag: 'sleep' },
    ' как я спал?',
  ]);
});

test('mid-text agent mention becomes a tag segment', () => {
  expect(parseAgentTags('try /workout for that')).toEqual([
    'try ',
    { tag: 'workout' },
    ' for that',
  ]);
});

test('unknown slash word stays as text', () => {
  expect(parseAgentTags('/usr/bin/sleep is unrelated')).toEqual([
    '/usr/bin/sleep is unrelated',
  ]);
});

test('multiple agent mentions are all parsed', () => {
  expect(parseAgentTags('/sleep then /nutrition')).toEqual([
    { tag: 'sleep' },
    ' then ',
    { tag: 'nutrition' },
  ]);
});

test('agent name not bounded by whitespace stays as text', () => {
  // /sleepwalker has /sleep as a prefix but isn't a known full word.
  expect(parseAgentTags('/sleepwalker')).toEqual(['/sleepwalker']);
});
