import en from '../../../../../packages/i18n/locales/en.json';
import ru from '../../../../../packages/i18n/locales/ru.json';
import { apiBaseUrl, apiMode } from '@/api/client';
import { getAuthHeaders } from '@/features/auth/getAuthHeaders';

export class VoiceError extends Error {
  constructor(public readonly code: string) {
    super(code);
  }
}

/** Upload one m4a recording and return its transcript, or an empty string for silence. */
export async function uploadRecording(uri: string, language: string): Promise<string> {
  if (apiMode === 'mock')
    return language === 'ru' ? ru.voice.mock_transcript : en.voice.mock_transcript;
  const form = new FormData();
  form.append('audio', { uri, name: 'voice.m4a', type: 'audio/m4a' } as unknown as Blob);
  form.append('language', language);
  const response = await fetch(`${apiBaseUrl}/voice/transcribe`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: form,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new VoiceError(body.detail ?? 'stt_unavailable');
  }
  return ((await response.json()) as { text: string }).text;
}
