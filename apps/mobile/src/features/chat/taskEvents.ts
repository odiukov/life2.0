import type { AgentId } from '@life-agents/ui';
import { isAgentId } from '../agents/agentStatusRules';

export type ActionStatus = 'pending' | 'applying' | 'applied' | 'rejected' | 'expired' | 'failed';
export type ActionState = {
  id: string;
  summary: string;
  expiresAt: string | null;
  status: ActionStatus;
  message?: string;
};

export type TaskEvent =
  | { type: 'text'; delta: string }
  | { type: 'routed'; primary: AgentId | null }
  | { type: 'consulted'; peers: AgentId[] }
  | { type: 'proposed'; action: ActionState }
  | { type: 'resolved'; actionId: string; status: ActionStatus; message: string }
  | { type: 'error'; code: string; message: string }
  | { type: 'finished' };

const STATUSES = new Set<ActionStatus>([
  'pending',
  'applying',
  'applied',
  'rejected',
  'expired',
  'failed',
]);
const str = (v: unknown) => (typeof v === 'string' ? v : '');

/** One SSE frame ("data: <json>") → an event the chat cares about, or null. */
export function parseSseFrame(frame: string): TaskEvent | null {
  for (const line of frame.split('\n')) {
    const t = line.trim();
    if (!t.startsWith('data:')) continue;
    let ev: Record<string, unknown>;
    try {
      ev = JSON.parse(t.slice(5).trimStart()) as Record<string, unknown>;
    } catch {
      return null;
    }
    if (!ev || typeof ev !== 'object' || Array.isArray(ev)) return null;
    switch (ev.type) {
      case 'TextMessageContent':
        return str(ev.delta) ? { type: 'text', delta: str(ev.delta) } : null;
      case 'AgentRouted':
        return { type: 'routed', primary: isAgentId(ev.primary) ? ev.primary : null };
      case 'AgentConsulted':
        return {
          type: 'consulted',
          peers: (Array.isArray(ev.peers) ? ev.peers : []).filter(isAgentId),
        };
      case 'ActionProposed':
        return {
          type: 'proposed',
          action: {
            id: str(ev.actionId),
            summary: str(ev.summary),
            expiresAt: str(ev.expiresAt) || null,
            status: 'pending',
          },
        };
      case 'ActionResolved': {
        const status = STATUSES.has(ev.status as ActionStatus)
          ? (ev.status as ActionStatus)
          : 'failed';
        return { type: 'resolved', actionId: str(ev.actionId), status, message: str(ev.message) };
      }
      case 'RunError':
        return { type: 'error', code: str(ev.code) || 'internal', message: str(ev.message) };
      case 'RunFinished':
        return { type: 'finished' };
      default:
        return null;
    }
  }
  return null;
}
