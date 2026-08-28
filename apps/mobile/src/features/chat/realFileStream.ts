/**
 * Sends a PDF file to POST /chat/file via multipart/form-data and reads back
 * the SSE response using the same XHR technique as realStream.ts.
 */
import { apiBaseUrl } from '@/api/client';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';
import type { StreamEvent } from './mockStream';

type QueueItem = { kind: 'event'; event: StreamEvent } | { kind: 'done' };

export async function* realFileStream(
  fileUri: string,
  fileName: string,
  threadId: string,
  agentHint?: string,
): AsyncGenerator<StreamEvent> {
  const queue: QueueItem[] = [];
  let waker: (() => void) | null = null;
  const push = (item: QueueItem) => {
    queue.push(item);
    const w = waker;
    waker = null;
    w?.();
  };
  const waitForItem = () => new Promise<void>((resolve) => { waker = resolve; });

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
        let ev: Record<string, unknown>;
        try { ev = JSON.parse(t.slice(6)) as Record<string, unknown>; } catch { continue; }
        if (ev.type === 'TextMessageContent') {
          const delta = typeof ev.delta === 'string' ? ev.delta : '';
          if (delta) push({ kind: 'event', event: { type: 'token', content: delta } });
        } else if (ev.type === 'RunFinished') {
          finish();
          return;
        }
      }
    }
  };

  const drainResponse = () => {
    const fresh = xhr.responseText.substring(consumed);
    consumed = xhr.responseText.length;
    if (fresh) processChunk(fresh);
  };

  const body = new FormData();
  body.append('file', { uri: fileUri, name: fileName, type: 'application/pdf' } as unknown as Blob);
  body.append('thread_id', threadId);
  if (agentHint) body.append('agent_hint', agentHint);

  const authHeaders = await getAuthHeaders();

  xhr.open('POST', `${apiBaseUrl}/chat/file`);
  xhr.setRequestHeader('Accept', 'text/event-stream');
  for (const [name, value] of Object.entries(authHeaders)) xhr.setRequestHeader(name, value);

  xhr.onprogress = () => drainResponse();
  xhr.onload = () => {
    drainResponse();
    if (xhr.status >= 400 && !streamEnded)
      push({ kind: 'event', event: { type: 'token', content: `[Server error: ${xhr.status}]` } });
    finish();
  };
  xhr.onerror = () => {
    if (!streamEnded)
      push({ kind: 'event', event: { type: 'token', content: '[Network error]' } });
    finish();
  };
  xhr.ontimeout = () => {
    if (!streamEnded)
      push({ kind: 'event', event: { type: 'token', content: '[Timeout]' } });
    finish();
  };

  xhr.send(body);

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
