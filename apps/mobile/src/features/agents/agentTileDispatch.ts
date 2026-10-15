import { openTask } from '../task/sheetStore';
import type { Router } from 'expo-router';
import type { AgentId } from '@life-agents/ui';
import type { IntegrationId } from '@/features/integrations/store';
import type { AgentRow } from './agentStatusRules';

export type TileDispatchContext = {
  router: Pick<Router, 'push'>;
  openIntegration: (panel: IntegrationId) => void;
  openDetail: (id: AgentId) => void;
  /** Opens the settings sheet on its integrations list. */
  openIntegrationsList: () => void;
};

export function dispatchTilePress(row: AgentRow, ctx: TileDispatchContext): void {
  if (!row.cta) {
    ctx.openDetail(row.id);
    return;
  }
  switch (row.cta.kind) {
    case 'integrations':
      if (row.cta.panel) ctx.openIntegration(row.cta.panel);
      return;
    case 'chat-prefill':
      openTask(
        row.cta.tag ? { lead: row.cta.tag, prefill: row.cta.text } : { prefill: row.cta.text },
      );
      return;
    case 'finance-upload':
      ctx.openIntegrationsList();
      return;
    default: {
      const _exhaustive: never = row.cta;
      return _exhaustive;
    }
  }
}
