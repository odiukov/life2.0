import { postSse, type StreamItem } from './sse';

class FakeXhr {
  static latest: FakeXhr;
  status = 200;
  responseText = '';
  onprogress?: () => void;
  onload?: () => void;
  onerror?: () => void;
  ontimeout?: () => void;
  open = jest.fn();
  setRequestHeader = jest.fn();
  send = jest.fn();
  abort = jest.fn();
  constructor() {
    FakeXhr.latest = this;
  }
  chunk(text: string) {
    this.responseText += text;
    this.onprogress?.();
  }
}

const originalXhr = global.XMLHttpRequest;
beforeEach(() => {
  global.XMLHttpRequest = FakeXhr as unknown as typeof XMLHttpRequest;
});
afterEach(() => {
  global.XMLHttpRequest = originalXhr;
});
const frame = (data: object) => `data: ${JSON.stringify(data)}\n\n`;
async function collect(events: AsyncGenerator<StreamItem>) {
  const result: StreamItem[] = [];
  for await (const event of events) result.push(event);
  return result;
}

function start() {
  const body = new FormData();
  const stream = postSse('/tasks/t1/messages', { Authorization: 'Bearer test' }, body);
  return { stream, xhr: FakeXhr.latest, body };
}

test('posts form data with authorization and emits chunked frames exactly once', async () => {
  const { stream, xhr, body } = start();
  expect(xhr.open).toHaveBeenCalledWith('POST', '/tasks/t1/messages');
  expect(xhr.setRequestHeader).toHaveBeenCalledWith('Accept', 'text/event-stream');
  expect(xhr.setRequestHeader).toHaveBeenCalledWith('Authorization', 'Bearer test');
  expect(xhr.send).toHaveBeenCalledWith(body);
  const text = frame({ type: 'TextMessageContent', delta: 'hello' });
  xhr.chunk(text.slice(0, 15));
  xhr.chunk(text.slice(15));
  xhr.onprogress?.();
  xhr.chunk(frame({ type: 'RunFinished' }));
  xhr.onload?.();
  expect(await collect(stream.events)).toEqual([
    { type: 'text', delta: 'hello' },
    { type: 'finished' },
  ]);
});

test.each(['\r\n', '\n'])(
  'accepts %j frame boundaries and data without a space',
  async (newline) => {
    const { stream, xhr } = start();
    const wire = `data:{"type":"TextMessageContent","delta":"hello"}${newline}${newline}data:{"type":"RunFinished"}${newline}${newline}`;
    for (const char of wire) xhr.chunk(char);
    xhr.onload?.();
    expect(await collect(stream.events)).toEqual([
      { type: 'text', delta: 'hello' },
      { type: 'finished' },
    ]);
  },
);

test('HTTP 409 yields a task_busy error without parsing error body as SSE', async () => {
  const { stream, xhr } = start();
  xhr.status = 409;
  xhr.chunk('{"detail":"task_busy"}');
  xhr.onload?.();
  expect(await collect(stream.events)).toEqual([
    { type: 'http_error', status: 409, code: 'task_busy' },
  ]);
});

test.each(['onerror', 'ontimeout'] as const)(
  '%s terminates with network error',
  async (handler) => {
    const { stream, xhr } = start();
    xhr[handler]?.();
    expect(await collect(stream.events)).toEqual([
      { type: 'http_error', status: 0, code: 'network' },
    ]);
  },
);

test('a successful HTTP response ending without RunFinished reports interrupted transport', async () => {
  const { stream, xhr } = start();
  xhr.chunk(frame({ type: 'TextMessageContent', delta: 'partial' }));
  xhr.onload?.();
  expect(await collect(stream.events)).toEqual([
    { type: 'text', delta: 'partial' },
    { type: 'http_error', status: 0, code: 'network' },
  ]);
});

test('abort releases a waiting consumer without reporting an error', async () => {
  const { stream, xhr } = start();
  const result = collect(stream.events);
  stream.abort();
  expect(xhr.abort).toHaveBeenCalledTimes(1);
  expect(await result).toEqual([]);
});
