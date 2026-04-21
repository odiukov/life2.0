/**
 * Real streaming client for the orchestrator /chat/stream SSE endpoint.
 *
 * Uses XMLHttpRequest with onreadystatechange (readyState=3) because React Native's
 * fetch() does not expose response.body as a stream — responseText accumulates
 * as the server sends chunks.
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
    waker?.();
  };
  const waitForItem = () =>
    new Promise<void>((resolve) => {
      waker = resolve;
    });

  const xhr = new XMLHttpRequest();
  let consumed = 0; // length of responseText already parsed
  let pendingBuffer = ''; // partial frame carry-over between reads
  let streamEnded = false;

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
        } else if (ev.type === 'RunFinished' && !streamEnded) {
          streamEnded = true;
          push({ kind: 'done' });
          return;
        }
        // RunStarted, TextMessageStart, TextMessageEnd — ignored.
      }
    }
  };

  xhr.open('POST', `${apiBaseUrl}/chat/stream`);
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.setRequestHeader('Accept', 'text/event-stream');

  xhr.onreadystatechange = () => {
    // readyState 3 (LOADING): responseText accumulating
    // readyState 4 (DONE): request finished (success or error)
    if (xhr.readyState === 3 || xhr.readyState === 4) {
      const fresh = xhr.responseText.substring(consumed);
      consumed = xhr.responseText.length;
      if (fresh) processChunk(fresh);
    }
    if (xhr.readyState === 4) {
      if (xhr.status >= 400 && !streamEnded) {
        push({ kind: 'event', event: { type: 'token', content: `[Server error: ${xhr.status}]` } });
      }
      if (!streamEnded) {
        streamEnded = true;
        push({ kind: 'done' });
      }
    }
  };

  xhr.onerror = () => {
    if (!streamEnded) {
      streamEnded = true;
      push({ kind: 'event', event: { type: 'token', content: '[Network error]' } });
      push({ kind: 'event', event: { type: 'done' } });
      push({ kind: 'done' });
    }
  };

  xhr.send(
    JSON.stringify({
      threadId,
      messages: [{ role: 'user', content: userText }],
    }),
  );

  // Consumer loop: yield queued events as they arrive.
  while (true) {
    while (queue.length > 0) {
      const item = queue.shift()!;
      if (item.kind === 'done') return;
      yield item.event;
    }
    await waitForItem();
  }
}
