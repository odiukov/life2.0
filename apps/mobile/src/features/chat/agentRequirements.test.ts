import { AGENT_REQUIRED_INTEGRATION, blockedAgents } from './agentRequirements';

test('mapping covers home and calendar only', () => {
  expect(AGENT_REQUIRED_INTEGRATION).toEqual({
    home: 'ha',
    calendar: 'calendar',
  });
});

test('blockedAgents returns home and calendar when nothing is connected', () => {
  const result = blockedAgents(new Set());
  expect(result).toEqual(new Set(['home', 'calendar']));
});

test('blockedAgents drops calendar when calendar is connected', () => {
  const result = blockedAgents(new Set(['calendar']));
  expect(result).toEqual(new Set(['home']));
});

test('blockedAgents drops home when ha is connected', () => {
  const result = blockedAgents(new Set(['ha']));
  expect(result).toEqual(new Set(['calendar']));
});

test('blockedAgents is empty when both are connected', () => {
  const result = blockedAgents(new Set(['ha', 'calendar']));
  expect(result.size).toBe(0);
});

test('unrelated connected integrations do not unblock anything', () => {
  const result = blockedAgents(new Set(['apple-health', 'garmin', 'yazio']));
  expect(result).toEqual(new Set(['home', 'calendar']));
});
