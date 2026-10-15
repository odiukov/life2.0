import { create } from 'zustand';
import type { AgentId } from '@life-agents/ui';
import type { OutgoingAttachment } from '@/features/chat/tasksApi';

export type Point = { x: number; y: number };
export type OpenRequest = {
  lead?: AgentId;
  prefill?: string;
  send?: string;
  voice?: { text: string; seconds: number };
  attachments?: OutgoingAttachment[];
  origin?: Point;
};
type State = {
  visible: boolean;
  origin: Point | null;
  pending: OpenRequest | null;
  queue: OpenRequest[];
  show(req?: OpenRequest): void;
  take(): OpenRequest | null;
  hide(): void;
};
const hasWork = (r: OpenRequest) =>
  Boolean(r.lead || r.prefill !== undefined || r.send || r.voice || r.attachments?.length);

/** Requests are consumed once in arrival order by the task sheet owner. */
export const useTaskSheet = create<State>((set, get) => ({
  visible: false,
  origin: null,
  pending: null,
  queue: [],
  show: (req) =>
    set((s) => {
      const queue = req && hasWork(req) ? [...s.queue, req] : s.queue;
      return { visible: true, origin: req?.origin ?? s.origin, queue, pending: queue[0] ?? null };
    }),
  take: () => {
    const request = get().pending;
    if (request) set((s) => ({ queue: s.queue.slice(1), pending: s.queue[1] ?? null }));
    return request;
  },
  hide: () => set({ visible: false, pending: null, queue: [] }),
}));
export const openTask = (req?: OpenRequest) => useTaskSheet.getState().show(req);
