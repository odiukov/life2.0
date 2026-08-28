import type { AgentId } from '@life-agents/ui';
import type { IntegrationId } from '../integrations/store';

export const AGENT_REQUIRED_INTEGRATION: Partial<Record<AgentId, IntegrationId>> = {
  home: 'ha',
  calendar: 'calendar',
};

export function blockedAgents(connected: ReadonlySet<IntegrationId>): Set<AgentId> {
  const blocked = new Set<AgentId>();
  for (const [agent, integration] of Object.entries(AGENT_REQUIRED_INTEGRATION) as [
    AgentId,
    IntegrationId,
  ][]) {
    if (!connected.has(integration)) blocked.add(agent);
  }
  return blocked;
}
