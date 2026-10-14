export const MIN_RECORDING_MS = 500;
export const MAX_RECORDING_MS = 60000;

export type VoiceState =
  | { phase: 'idle'; discarded?: boolean }
  | { phase: 'recording'; startedAt: number }
  | { phase: 'transcribing' };

export type VoiceEvent =
  | { type: 'start'; at: number }
  | { type: 'stop'; at: number }
  | { type: 'done' };

export function voiceReducer(state: VoiceState, event: VoiceEvent): VoiceState {
  switch (event.type) {
    case 'start':
      return state.phase === 'idle' ? { phase: 'recording', startedAt: event.at } : state;
    case 'stop':
      if (state.phase !== 'recording') return state;
      return event.at - state.startedAt < MIN_RECORDING_MS
        ? { phase: 'idle', discarded: true }
        : { phase: 'transcribing' };
    case 'done':
      return { phase: 'idle' };
  }
}

/** Append the transcript to text already typed by the user. */
export function mergeTranscript(draft: string, text: string): string {
  const head = draft.trimEnd();
  return head ? `${head} ${text.trim()}` : text.trim();
}
