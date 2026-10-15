import { parseSseFrame, type TaskEvent } from './taskEvents';

export type StreamItem = TaskEvent | { type: 'http_error'; status: number; code: string };
export type MessageStream = { events: AsyncGenerator<StreamItem>; abort(): void };

/** POST `body` and yield SSE events until RunFinished, an HTTP error or abort(). */
export function postSse(
  url: string,
  headers: Record<string, string>,
  body: FormData,
): MessageStream {
  const queue: (StreamItem | null)[] = [];
  let wake: (() => void) | null = null;
  let ended = false;
  let consumed = 0;
  let buffer = '';
  const push = (item: StreamItem | null) => {
    if (ended && item !== null) return;
    queue.push(item);
    const w = wake;
    wake = null;
    w?.();
  };
  const end = () => {
    if (!ended) {
      ended = true;
      push(null);
    }
  };
  const xhr = new XMLHttpRequest();
  const drain = () => {
    if (ended || xhr.status >= 400) return; // the error body is read in onload
    const fresh = xhr.responseText.substring(consumed);
    consumed = xhr.responseText.length;
    buffer += fresh;
    const frames = buffer.split(/\r?\n\r?\n/);
    buffer = frames.pop() ?? '';
    for (const frame of frames) {
      const ev = parseSseFrame(frame);
      if (ev) push(ev);
      if (ev?.type === 'finished') return end();
    }
  };
  xhr.open('POST', url);
  xhr.setRequestHeader('Accept', 'text/event-stream');
  for (const [k, v] of Object.entries(headers)) xhr.setRequestHeader(k, v);
  xhr.onprogress = drain;
  xhr.onload = () => {
    if (ended) return;
    if (xhr.status >= 400) {
      let code = 'http';
      try {
        const detail = (JSON.parse(xhr.responseText) as { detail?: unknown }).detail;
        if (typeof detail === 'string') code = detail;
      } catch {
        /* not JSON */
      }
      push({ type: 'http_error', status: xhr.status, code });
    } else {
      drain();
      if (!ended) push({ type: 'http_error', status: 0, code: 'network' });
    }
    end();
  };
  xhr.onerror = () => {
    push({ type: 'http_error', status: 0, code: 'network' });
    end();
  };
  xhr.ontimeout = xhr.onerror;
  xhr.send(body);

  async function* events(): AsyncGenerator<StreamItem> {
    while (true) {
      while (queue.length) {
        const item = queue.shift()!;
        if (item === null) return;
        yield item;
      }
      if (ended) return;
      await new Promise<void>((r) => (wake = r));
    }
  }
  return {
    events: events(),
    abort: () => {
      xhr.abort();
      end();
    },
  };
}
