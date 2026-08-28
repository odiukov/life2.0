import type { StreamEvent } from './mockStream';

test('StreamEvent union includes agent_routed and agent_consulted', () => {
  // Compile-time check: these constructions must satisfy StreamEvent.
  const routed: StreamEvent = { type: 'agent_routed', primary: 'sleep' };
  const consulted: StreamEvent = { type: 'agent_consulted', peers: ['nutrition'] };
  expect(routed.type).toBe('agent_routed');
  expect(consulted.type).toBe('agent_consulted');
});
