/**
 * Real streaming client for the orchestrator SSE endpoints.
 *
 * Two routes:
 *   POST /chat/stream                    — freeform; LangGraph orchestrator decides routing.
 *   POST /agent/{name}/stream            — slash-tagged; pass-through to a single peer.
 *
 * Uses XMLHttpRequest with onprogress because React Native's fetch() does not
 * expose response.body as a ReadableStream — responseText accumulates as the
 * server sends chunks; we diff against `consumed` to extract each delta.
 */
import { chatStreamUrl, passthroughChatUrl } from '@/api/client';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';
import type { AgentId } from '@life-agents/ui';
import type { StreamEvent } from './mockStream';

/** Parse a single SSE frame ("data: <json>\n…") into a StreamEvent, or null if ignored. */
export function _parseSseFrame(frame: string): StreamEvent | null {
  for (const line of frame.split('\n')) {
    const t = line.trim();
    if (!t.startsWith('data: ')) continue;
    let ev: Record<string, unknown>;
    try {
      ev = JSON.parse(t.slice(6)) as Record<string, unknown>;
    } catch {
      continue;
    }
    switch (ev.type) {
      case 'TextMessageContent': {
        const delta = typeof ev.delta === 'string' ? ev.delta : '';
        return delta ? { type: 'token', content: delta } : null;
      }
      case 'AgentRouted':
        return { type: 'agent_routed', primary: ev.primary as AgentId };
      case 'AgentConsulted':
        return { type: 'agent_consulted', peers: (ev.peers as AgentId[]) ?? [] };
      default:
        return null; // RunStarted, TextMessageStart, TextMessageEnd, RunFinished — ignored
    }
  }
  return null;
}

type QueueItem = { kind: 'event'; event: StreamEvent } | { kind: 'done' };

export async function* realAssistantStream(
  userText: string,
  threadId: string,
  opts?: { agent?: AgentId },
): AsyncGenerator<StreamEvent> {
  const queue: QueueItem[] = [];
  let waker: (() => void) | null = null;
  const push = (item: QueueItem) => {
    queue.push(item);
    const w = waker;
    waker = null;
    w?.();
  };
  const waitForItem = () =>
    new Promise<void>((resolve) => {
      waker = resolve;
    });

  const xhr = new XMLHttpRequest();
  let consumed = 0;
  let pendingBuffer = '';
  let streamEnded = false;

  const finish = () => {
    if (streamEnded) return;
    streamEnded = true;
    push({ kind: 'event', event: { type: 'done' } });
    push({ kind: 'done' });
  };

  const processChunk = (newText: string) => {
    pendingBuffer += newText;
    const frames = pendingBuffer.split('\n\n');
    pendingBuffer = frames.pop() ?? '';
    for (const frame of frames) {
      const ev = _parseSseFrame(frame);
      if (ev) push({ kind: 'event', event: ev });
      // Detect the stream-ending frame to call finish() promptly.
      if (frame.includes('"RunFinished"')) {
        finish();
        return;
      }
    }
  };

  const drainResponse = () => {
    const fresh = xhr.responseText.substring(consumed);
    consumed = xhr.responseText.length;
    if (fresh) processChunk(fresh);
  };

  const authHeaders = await getAuthHeaders();
  const url = opts?.agent ? passthroughChatUrl(opts.agent) : chatStreamUrl();

  xhr.open('POST', url);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.setRequestHeader('Accept', 'text/event-stream');
  for (const [name, value] of Object.entries(authHeaders)) xhr.setRequestHeader(name, value);

  xhr.onprogress = () => drainResponse();
  xhr.onload = () => {
    drainResponse();
    if (xhr.status >= 400 && !streamEnded) {
      push({
        kind: 'event',
        event: { type: 'token', content: `[Server error: ${xhr.status}]` },
      });
    }
    finish();
  };
  xhr.onerror = () => {
    if (!streamEnded) {
      push({ kind: 'event', event: { type: 'token', content: '[Network error]' } });
    }
    finish();
  };
  xhr.ontimeout = () => {
    if (!streamEnded) {
      push({ kind: 'event', event: { type: 'token', content: '[Timeout]' } });
    }
    finish();
  };

  xhr.send(
    JSON.stringify({
      threadId,
      userTimezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      messages: [{ role: 'user', content: userText }],
    }),
  );

  while (true) {
    while (queue.length > 0) {
      const item = queue.shift()!;
      if (item.kind === 'done') return;
      yield item.event;
    }
    if (streamEnded && queue.length === 0) return;
    await waitForItem();
  }
}
