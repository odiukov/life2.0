import { act, renderHook, waitFor } from '@testing-library/react-native';
import { AudioModule, setAudioModeAsync, useAudioRecorder } from 'expo-audio';
import { useVoiceInput } from './useVoiceInput';
import { uploadRecording } from './upload';

jest.mock('./upload', () => ({
  uploadRecording: jest.fn(async () => 'bought bread'),
  VoiceError: class VoiceError extends Error {},
}));

const recorder = useAudioRecorder({
  extension: '.m4a',
  sampleRate: 16000,
  numberOfChannels: 1,
  bitRate: 32000,
  android: { outputFormat: 'mpeg4', audioEncoder: 'aac' },
  ios: { audioQuality: 64 },
  web: {},
});
const permission = AudioModule.requestRecordingPermissionsAsync as jest.Mock;
const audioMode = setAudioModeAsync as jest.Mock;
const upload = uploadRecording as jest.Mock;

beforeEach(() => {
  jest.useFakeTimers();
  jest.setSystemTime(0);
  permission.mockReset().mockResolvedValue({ granted: true });
  audioMode.mockReset().mockResolvedValue(undefined);
  jest.mocked(recorder.prepareToRecordAsync).mockReset().mockResolvedValue(undefined);
  jest.mocked(recorder.record).mockReset();
  jest.mocked(recorder.stop).mockReset().mockResolvedValue(undefined);
  upload.mockReset().mockResolvedValue('bought bread');
});

afterEach(() => jest.useRealTimers());

test('a released hold while permission is pending never starts recording', async () => {
  let resolvePermission!: (value: { granted: boolean }) => void;
  permission.mockReturnValue(
    new Promise((resolve) => {
      resolvePermission = resolve;
    }),
  );
  const onTranscript = jest.fn();
  const { result } = renderHook(() => useVoiceInput({ onTranscript, onNotice: jest.fn() }));
  let start!: Promise<void>;
  act(() => {
    start = result.current.start();
    result.current.stop();
  });
  await act(async () => {
    resolvePermission({ granted: true });
    await start;
  });
  expect(recorder.record).not.toHaveBeenCalled();
  expect(result.current.state).toBe('idle');
  expect(onTranscript).not.toHaveBeenCalled();
});

test('release during recorder preparation cancels the capture', async () => {
  let resolvePrepare!: () => void;
  jest.mocked(recorder.prepareToRecordAsync).mockReturnValue(
    new Promise((resolve) => {
      resolvePrepare = resolve;
    }),
  );
  const { result } = renderHook(() =>
    useVoiceInput({ onTranscript: jest.fn(), onNotice: jest.fn() }),
  );
  let start!: Promise<void>;
  await act(async () => {
    start = result.current.start();
    await Promise.resolve();
  });
  act(() => {
    result.current.stop();
  });
  await act(async () => {
    resolvePrepare();
    await start;
  });
  expect(result.current.state).toBe('idle');
  expect(recorder.stop).toHaveBeenCalledTimes(1);
  expect(upload).not.toHaveBeenCalled();
});

test('one-minute cap stops the current recorder and transcribes', async () => {
  const onTranscript = jest.fn();
  const { result } = renderHook(() => useVoiceInput({ onTranscript, onNotice: jest.fn() }));
  await act(async () => {
    await result.current.start();
  });
  expect(result.current.state).toBe('recording');
  await act(async () => {
    jest.advanceTimersByTime(60000);
    await Promise.resolve();
  });
  await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('bought bread'));
  expect(recorder.stop).toHaveBeenCalledTimes(1);
  expect(result.current.state).toBe('idle');
});

test('short hold is discarded and duplicate start/stop do not upload', async () => {
  const { result } = renderHook(() =>
    useVoiceInput({ onTranscript: jest.fn(), onNotice: jest.fn() }),
  );
  await act(async () => {
    await result.current.start();
    await result.current.start();
  });
  await act(async () => {
    jest.advanceTimersByTime(200);
    await result.current.stop();
    await result.current.stop();
  });
  expect(recorder.record).toHaveBeenCalledTimes(1);
  expect(recorder.stop).toHaveBeenCalledTimes(1);
  expect(upload).not.toHaveBeenCalled();
  expect(result.current.state).toBe('idle');
});

test('unmount clears cap and stops active recorder without upload', async () => {
  const { result, unmount } = renderHook(() =>
    useVoiceInput({ onTranscript: jest.fn(), onNotice: jest.fn() }),
  );
  await act(async () => {
    await result.current.start();
  });
  const activeTimers = jest.getTimerCount();
  unmount();
  expect(jest.getTimerCount()).toBeLessThan(activeTimers);
  await act(async () => {
    jest.advanceTimersByTime(60000);
    await Promise.resolve();
  });
  expect(recorder.stop).toHaveBeenCalledTimes(1);
  expect(upload).not.toHaveBeenCalled();
});

test('a new hold waits until the previous audio session has closed', async () => {
  let closeSession!: () => void;
  audioMode.mockImplementation(({ allowsRecording }: { allowsRecording: boolean }) =>
    allowsRecording
      ? Promise.resolve()
      : new Promise<void>((resolve) => {
          closeSession = resolve;
        }),
  );
  const { result } = renderHook(() =>
    useVoiceInput({ onTranscript: jest.fn(), onNotice: jest.fn() }),
  );
  await act(async () => {
    await result.current.start();
  });
  let stop!: Promise<void>;
  act(() => {
    jest.advanceTimersByTime(700);
    stop = result.current.stop();
  });
  await act(async () => {
    await Promise.resolve();
  });
  const permissionCalls = permission.mock.calls.length;
  await act(async () => {
    await result.current.start();
  });
  expect(permission).toHaveBeenCalledTimes(permissionCalls);
  await act(async () => {
    closeSession();
    await stop;
  });
  await act(async () => {
    await result.current.start();
  });
  expect(permission).toHaveBeenCalledTimes(permissionCalls + 1);
});

test('a cancelled start remains busy until recorder and audio-mode cleanup finish', async () => {
  let finishPrepare!: () => void;
  let finishStop!: () => void;
  let finishMode!: () => void;
  jest.mocked(recorder.prepareToRecordAsync).mockReturnValue(
    new Promise((resolve) => {
      finishPrepare = resolve;
    }),
  );
  jest.mocked(recorder.stop).mockReturnValue(
    new Promise((resolve) => {
      finishStop = resolve;
    }),
  );
  audioMode.mockImplementation(({ allowsRecording }: { allowsRecording: boolean }) =>
    allowsRecording
      ? Promise.resolve()
      : new Promise<void>((resolve) => {
          finishMode = resolve;
        }),
  );
  const { result } = renderHook(() =>
    useVoiceInput({ onTranscript: jest.fn(), onNotice: jest.fn() }),
  );
  let firstStart!: Promise<void>;
  await act(async () => {
    firstStart = result.current.start();
    await Promise.resolve();
  });
  act(() => {
    result.current.stop();
  });
  await act(async () => {
    finishPrepare();
    await Promise.resolve();
  });
  const permissionCalls = permission.mock.calls.length;
  await act(async () => {
    await result.current.start();
  });
  expect(permission).toHaveBeenCalledTimes(permissionCalls);
  await act(async () => {
    finishStop();
    await Promise.resolve();
  });
  await act(async () => {
    await result.current.start();
  });
  expect(permission).toHaveBeenCalledTimes(permissionCalls);
  await act(async () => {
    finishMode();
    await firstStart;
  });
  await act(async () => {
    await result.current.start();
  });
  expect(permission).toHaveBeenCalledTimes(permissionCalls + 1);
});
