import { _parseSseFrame } from './realStream';

test('parses TextMessageContent frame to token event', () => {
  expect(
    _parseSseFrame('data: {"type":"TextMessageContent","delta":"hi"}'),
  ).toEqual({ type: 'token', content: 'hi' });
});

test('parses AgentRouted frame to agent_routed event', () => {
  expect(
    _parseSseFrame('data: {"type":"AgentRouted","primary":"sleep"}'),
  ).toEqual({ type: 'agent_routed', primary: 'sleep' });
});

test('parses AgentConsulted frame to agent_consulted event', () => {
  expect(
    _parseSseFrame('data: {"type":"AgentConsulted","peers":["nutrition","workout"]}'),
  ).toEqual({ type: 'agent_consulted', peers: ['nutrition', 'workout'] });
});

test('returns null for ignored frame types', () => {
  expect(
    _parseSseFrame('data: {"type":"RunStarted","threadId":"x"}'),
  ).toBeNull();
});
