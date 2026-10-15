import type { AgentId } from '@life-agents/ui';
import type { IntegrationId } from '../integrations/store';

export const BASE_LEADS: readonly AgentId[] = [
  'nutrition',
  'kitchen',
  'sleep',
  'workout',
  'medication',
  'mood',
];

export function quickLeads(connected: ReadonlySet<IntegrationId>): AgentId[] {
  return [
    ...BASE_LEADS,
    ...(connected.has('calendar') ? (['calendar'] as const) : []),
    ...(connected.has('ha') ? (['home'] as const) : []),
  ];
}
