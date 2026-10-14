import { getAuthHeaders } from '@/features/auth/getAuthHeaders';
import { uploadRecording } from './upload';

jest.mock('@/api/client', () => ({ apiMode: 'local', apiBaseUrl: 'http://localhost:8000' }));
jest.mock('@/features/auth/getAuthHeaders', () => ({
  getAuthHeaders: jest.fn(async () => ({ Authorization: 'Bearer test-token' })),
}));

const originalFetch = global.fetch;
const originalFormData = global.FormData;

class RecordingFormData {
  readonly parts: Array<[string, unknown]> = [];
  append(name: string, value: unknown) {
    this.parts.push([name, value]);
  }
}

beforeEach(() => {
  global.FormData = RecordingFormData as unknown as typeof FormData;
  jest.clearAllMocks();
});

afterEach(() => {
  global.fetch = originalFetch;
  global.FormData = originalFormData;
});

test('uploads an authenticated m4a multipart body without overriding its boundary', async () => {
  const request = jest.fn(async () => ({ ok: true, json: async () => ({ text: 'bought bread' }) }));
  global.fetch = request as unknown as typeof fetch;

  expect(await uploadRecording('file:///recording.m4a', 'en')).toBe('bought bread');
  expect(getAuthHeaders).toHaveBeenCalledTimes(1);
  const [url, init] = request.mock.calls[0] as unknown as [string, RequestInit];
  expect(url).toBe('http://localhost:8000/voice/transcribe');
  expect(init.method).toBe('POST');
  expect(init.headers).toEqual({ Authorization: 'Bearer test-token' });
  const body = init.body as unknown as RecordingFormData;
  expect(body.parts).toEqual([
    ['audio', { uri: 'file:///recording.m4a', name: 'voice.m4a', type: 'audio/m4a' }],
    ['language', 'en'],
  ]);
});

test('preserves gateway error codes and uses a fallback for unreadable errors', async () => {
  const request = jest
    .fn()
    .mockResolvedValueOnce({ ok: false, json: async () => ({ detail: 'audio_too_long' }) })
    .mockResolvedValueOnce({
      ok: false,
      json: async () => {
        throw new Error('bad json');
      },
    });
  global.fetch = request as unknown as typeof fetch;

  await expect(uploadRecording('file:///recording.m4a', 'en')).rejects.toMatchObject({
    code: 'audio_too_long',
  });
  await expect(uploadRecording('file:///recording.m4a', 'en')).rejects.toMatchObject({
    code: 'stt_unavailable',
  });
});
