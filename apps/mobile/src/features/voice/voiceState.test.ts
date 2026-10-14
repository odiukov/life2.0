import { MAX_RECORDING_MS, mergeTranscript, voiceReducer } from './voiceState';

test('recording transitions to transcription and back', () => {
  const recording = voiceReducer({ phase: 'idle' }, { type: 'start', at: 0 });
  expect(recording).toEqual({ phase: 'recording', startedAt: 0 });
  expect(voiceReducer(recording, { type: 'stop', at: 1200 })).toEqual({ phase: 'transcribing' });
  expect(voiceReducer({ phase: 'transcribing' }, { type: 'done' })).toEqual({ phase: 'idle' });
});

test('short recording is discarded and busy actions are ignored', () => {
  const recording = voiceReducer({ phase: 'idle' }, { type: 'start', at: 0 });
  expect(voiceReducer(recording, { type: 'stop', at: 300 })).toEqual({
    phase: 'idle',
    discarded: true,
  });
  expect(voiceReducer({ phase: 'idle' }, { type: 'stop', at: 1 })).toEqual({ phase: 'idle' });
  expect(voiceReducer({ phase: 'transcribing' }, { type: 'start', at: 1 })).toEqual({
    phase: 'transcribing',
  });
});

test('recording cap is one minute', () => {
  expect(MAX_RECORDING_MS).toBe(60000);
});

test.each([
  ['', 'bought bread', 'bought bread'],
  ['and milk', 'bought bread', 'and milk bought bread'],
  ['ends with space ', 'x', 'ends with space x'],
])('merges transcript with draft', (draft, text, expected) => {
  expect(mergeTranscript(draft, text)).toBe(expected);
});
