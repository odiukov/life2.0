import { AGENT_COLORS, agentSolid, agentTint } from './agentColors';

test('all agent ids have color entries', () => {
  const ids = ['sleep','workout','nutrition','mood','habits','medication','recovery','calendar','finance','home','body'] as const;
  ids.forEach(id => expect(AGENT_COLORS[id]).toBeDefined());
});
test('agentSolid returns hex string', () => {
  expect(agentSolid('sleep')).toMatch(/^#/);
});
test('agentTint returns hex string with alpha', () => {
  expect(agentTint('sleep')).toMatch(/^#/);
});
