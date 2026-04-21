/**
 * Real streaming client for the orchestrator /chat/stream SSE endpoint.
 *
 * Uses XMLHttpRequest with onprogress because React Native's fetch() does not
 * expose response.body as a ReadableStream — responseText accumulates as the
 * server sends chunks; we diff against `consumed` to extract each delta.
 */
import { apiBaseUrl } from '@/api/client';
import type { StreamEvent } from './mockStream';

export const THREAD_ID = 'mobile-' + Date.now();

type QueueItem = { kind: 'event'; event: StreamEvent } | { kind: 'done' };

export async function* realAssistantStream(
  userText: string,
  threadId: string = THREAD_ID,
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
      for (const line of frame.split('\n')) {
        const t = line.trim();
        if (!t.startsWith('data: ')) continue;
        const jsonStr = t.slice(6);
        let ev: Record<string, unknown>;
        try {
          ev = JSON.parse(jsonStr) as Record<string, unknown>;
        } catch {
          continue;
        }
        if (ev.type === 'TextMessageContent') {
          const delta = typeof ev.delta === 'string' ? ev.delta : '';
          if (delta) push({ kind: 'event', event: { type: 'token', content: delta } });
        } else if (ev.type === 'RunFinished') {
          finish();
          return;
        }
        // RunStarted, TextMessageStart, TextMessageEnd — ignored.
      }
    }
  };

  const drainResponse = () => {
    const fresh = xhr.responseText.substring(consumed);
    consumed = xhr.responseText.length;
    if (fresh) processChunk(fresh);
  };

  xhr.open('POST', `${apiBaseUrl}/chat/stream`);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.setRequestHeader('Accept', 'text/event-stream');

  xhr.onprogress = () => {
    drainResponse();
  };

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
