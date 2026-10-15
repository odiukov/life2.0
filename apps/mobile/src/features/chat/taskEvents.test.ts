import { parseSseFrame } from './taskEvents';

const frame = (data: object) => `data: ${JSON.stringify(data)}`;

test('text, routing and consulted peers', () => {
  expect(parseSseFrame(frame({ type: 'TextMessageContent', delta: 'Hi' }))).toEqual({
    type: 'text',
    delta: 'Hi',
  });
  expect(parseSseFrame(frame({ type: 'AgentRouted', primary: 'sleep' }))).toEqual({
    type: 'routed',
    primary: 'sleep',
  });
  expect(parseSseFrame(frame({ type: 'AgentRouted', primary: 'main' }))).toEqual({
    type: 'routed',
    primary: null,
  });
  expect(
    parseSseFrame(frame({ type: 'AgentConsulted', peers: ['nutrition', 'astrology'] })),
  ).toEqual({ type: 'consulted', peers: ['nutrition'] });
});

test('actions and errors', () => {
  expect(
    parseSseFrame(
      frame({
        type: 'ActionProposed',
        actionId: 'a1',
        summary: 'Выключить: Lamp?',
        expiresAt: '2026-10-14T18:05:00Z',
      }),
    ),
  ).toEqual({
    type: 'proposed',
    action: {
      id: 'a1',
      summary: 'Выключить: Lamp?',
      expiresAt: '2026-10-14T18:05:00Z',
      status: 'pending',
    },
  });
  expect(
    parseSseFrame(
      frame({ type: 'ActionResolved', actionId: 'a1', status: 'applied', message: 'Готово.' }),
    ),
  ).toEqual({
    type: 'resolved',
    actionId: 'a1',
    status: 'applied',
    message: 'Готово.',
  });
  expect(
    parseSseFrame(frame({ type: 'RunError', code: 'timeout', message: 'Слишком долго.' })),
  ).toEqual({ type: 'error', code: 'timeout', message: 'Слишком долго.' });
  expect(parseSseFrame(frame({ type: 'RunFinished' }))).toEqual({ type: 'finished' });
});

test('ignored and broken frames', () => {
  expect(parseSseFrame(frame({ type: 'RunStarted' }))).toBeNull();
  expect(parseSseFrame(frame({ type: 'TextMessageContent', delta: '' }))).toBeNull();
  expect(parseSseFrame('data: {not json')).toBeNull();
  expect(parseSseFrame(': keep-alive')).toBeNull();
});

test('kitchen is a supported lead and malformed JSON values are ignored', () => {
  expect(parseSseFrame(frame({ type: 'AgentRouted', primary: 'kitchen' }))).toEqual({
    type: 'routed',
    primary: 'kitchen',
  });
  expect(parseSseFrame('data: null')).toBeNull();
  expect(parseSseFrame('data: []')).toBeNull();
});

test('an in-progress action stays applying instead of claiming failure', () => {
  expect(
    parseSseFrame(
      frame({ type: 'ActionResolved', actionId: 'a1', status: 'applying', message: 'Applying' }),
    ),
  ).toEqual({ type: 'resolved', actionId: 'a1', status: 'applying', message: 'Applying' });
});
