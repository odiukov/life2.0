import type { AgentId } from '@life-agents/ui';
export const AGENT_ORDER: AgentId[] = [
  'recovery',
  'sleep',
  'workout',
  'nutrition',
  'mood',
  'habits',
  'medication',
  'body',
  'calendar',
  'finance',
  'home',
];
export const DETAIL_AGENTS: ReadonlySet<AgentId> = new Set([
  'sleep',
  'workout',
  'nutrition',
  'mood',
  'habits',
  'recovery',
  'medication',
  'finance',
  'calendar',
]);
