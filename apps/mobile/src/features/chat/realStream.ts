/**
 * Real streaming client for the orchestrator /chat/stream SSE endpoint.
 *
 * Format: SSE — each frame is `data: <JSON>\n\n`.
 * Relevant event types:
 *   - TextMessageContent  → { delta: string }  → yield token
 *   - RunFinished         → yield done
 * All other frame types (RunStarted, TextMessageStart, TextMessageEnd) are ignored.
 */
import { apiBaseUrl } from '@/api/client';
import type { StreamEvent } from './mockStream';

export const THREAD_ID = 'mobile-' + Date.now();

export async function* realAssistantStream(
  userText: string,
  threadId: string = THREAD_ID,
): AsyncGenerator<StreamEvent> {
  let res: Response;
  try {
    res = await fetch(`${apiBaseUrl}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        threadId,
        messages: [{ role: 'user', content: userText }],
      }),
    });
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    yield { type: 'token', content: `[Network error: ${msg}]` };
    yield { type: 'done' };
    return;
  }

  if (!res.ok) {
    yield { type: 'token', content: `[Server error: ${res.status} ${res.statusText}]` };
    yield { type: 'done' };
    return;
  }

  if (!res.body) {
    yield { type: 'token', content: '[Error: no response body]' };
    yield { type: 'done' };
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by double-newline (\n\n).
      // Split on double-newline but keep trailing incomplete frame in buffer.
      const frames = buffer.split('\n\n');
      // Last element may be incomplete — keep it in the buffer.
      buffer = frames.pop() ?? '';

      for (const frame of frames) {
        for (const line of frame.split('\n')) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data: ')) continue;
          const jsonStr = trimmed.slice(6);
          let event: Record<string, unknown>;
          try {
            event = JSON.parse(jsonStr) as Record<string, unknown>;
          } catch {
            // Incomplete JSON in this line — skip (shouldn't happen with SSE).
            continue;
          }

          if (event.type === 'TextMessageContent') {
            const delta = typeof event.delta === 'string' ? event.delta : '';
            if (delta) {
              yield { type: 'token', content: delta };
            }
          } else if (event.type === 'RunFinished') {
            yield { type: 'done' };
            return;
          }
          // RunStarted, TextMessageStart, TextMessageEnd — ignored.
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  // Stream ended without RunFinished (shouldn't happen, but be safe).
  yield { type: 'done' };
}
