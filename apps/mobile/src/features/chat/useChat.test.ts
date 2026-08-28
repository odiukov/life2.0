import { renderHook, act } from '@testing-library/react-native';
import { useChat } from './useChat';

jest.mock('./realFileStream', () => ({
  realFileStream: jest.fn(async function* () {
    yield { type: 'token', content: 'Импортировал 1 измерение.' };
    yield { type: 'done' };
  }),
}));

const mockRealAssistantStream = jest.fn(async function* (
  _text: string,
  _thread: string,
  _opts?: { agent?: string },
) {
  yield { type: 'agent_routed', primary: 'sleep' };
  yield { type: 'token', content: 'You slept ' };
  yield { type: 'token', content: '7h.' };
  yield { type: 'agent_consulted', peers: ['nutrition'] };
  yield { type: 'done' };
});

jest.mock('./realStream', () => ({
  realAssistantStream: (text: string, thread: string, opts?: { agent?: string }) =>
    mockRealAssistantStream(text, thread, opts),
}));

beforeEach(() => {
  mockRealAssistantStream.mockClear();
});

test('sendFile adds user filename bubble and assistant response', async () => {
  const { result } = renderHook(() => useChat());
  await act(async () => {
    await result.current.sendFile('file:///tmp/test.pdf', 'test.pdf');
  });
  const messages = result.current.messages;
  expect(messages.some((m) => m.kind === 'user' && m.text.includes('test.pdf'))).toBe(true);
  expect(messages.some((m) => m.kind === 'assistant' && m.text.includes('Импортировал'))).toBe(
    true,
  );
});

test('user tag is preserved on user message; assistant agent + consulted set from stream', async () => {
  const { result } = renderHook(() => useChat());
  await act(async () => {
    await result.current.send({ tag: 'sleep', text: 'how did I sleep' });
  });
  const messages = result.current.messages;
  const userMsg = messages.find((m) => m.kind === 'user');
  expect(userMsg).toMatchObject({ kind: 'user', tag: 'sleep', text: 'how did I sleep' });
  const asstMsg = messages.find((m) => m.kind === 'assistant');
  expect(asstMsg).toMatchObject({
    kind: 'assistant',
    agent: 'sleep',
    consulted: ['nutrition'],
    text: 'You slept 7h.',
  });
});

test('send(string) with leading agent slash routes via pass-through', async () => {
  const { result } = renderHook(() => useChat());
  await act(async () => {
    await result.current.send('/workout analyze my session');
  });
  expect(mockRealAssistantStream).toHaveBeenCalledTimes(1);
  expect(mockRealAssistantStream).toHaveBeenCalledWith('analyze my session', expect.any(String), {
    agent: 'workout',
  });
  const userMsg = result.current.messages.find((m) => m.kind === 'user');
  expect(userMsg).toMatchObject({ kind: 'user', tag: 'workout', text: 'analyze my session' });
});

test('send(string) with /calendar keeps the slash text on orchestrator chat route', async () => {
  const { result } = renderHook(() => useChat());
  await act(async () => {
    await result.current.send('/calendar what is today');
  });
  expect(mockRealAssistantStream).toHaveBeenCalledTimes(1);
  expect(mockRealAssistantStream).toHaveBeenCalledWith(
    '/calendar what is today',
    expect.any(String),
    undefined,
  );
  const userMsg = result.current.messages.find((m) => m.kind === 'user');
  expect(userMsg).toMatchObject({
    kind: 'user',
    tag: 'calendar',
    text: 'what is today',
  });
});

test('send(string) without slash goes to orchestrator path with tag undefined', async () => {
  const { result } = renderHook(() => useChat());
  await act(async () => {
    await result.current.send('plain question');
  });
  expect(mockRealAssistantStream).toHaveBeenCalledWith(
    'plain question',
    expect.any(String),
    undefined,
  );
  const userMsg = result.current.messages.find((m) => m.kind === 'user');
  expect(userMsg).toMatchObject({ kind: 'user', tag: undefined, text: 'plain question' });
});

test('send(string) with unknown slash-name is treated as plain text', async () => {
  const { result } = renderHook(() => useChat());
  await act(async () => {
    await result.current.send('/notanagent foo');
  });
  expect(mockRealAssistantStream).toHaveBeenCalledWith(
    '/notanagent foo',
    expect.any(String),
    undefined,
  );
});
