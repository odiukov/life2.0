import { act, renderHook, waitFor } from '@testing-library/react-native';
import { AudioModule, setAudioModeAsync, useAudioRecorder } from 'expo-audio';
import { meteringLevel, useVoiceInput } from './useVoiceInput';
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
  await waitFor(() => expect(onTranscript).toHaveBeenCalledWith('bought bread', 60));
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

test.each([
  [undefined, 0],
  [null, 0],
  [-80, 0],
  [-60, 0],
  [-30, 0.5],
  [0, 1],
  [6, 1],
])('metering %p becomes %p', (db, level) => {
  expect(meteringLevel(db)).toBeCloseTo(level);
});

test('cancel stops recording without uploading', async () => {
  const onTranscript = jest.fn();
  const { result } = renderHook(() => useVoiceInput({ onTranscript, onNotice: jest.fn() }));
  await act(async () => {
    await result.current.start();
  });
  await act(async () => {
    jest.advanceTimersByTime(2000);
    await result.current.cancel();
  });
  expect(recorder.stop).toHaveBeenCalledTimes(1);
  expect(upload).not.toHaveBeenCalled();
  expect(onTranscript).not.toHaveBeenCalled();
  expect(result.current.state).toBe('idle');
});

test('cancel during deferred upload suppresses late transcript and notice', async () => {
  let finish!: (text: string) => void;
  upload.mockReturnValue(
    new Promise<string>((resolve) => {
      finish = resolve;
    }),
  );
  const onTranscript = jest.fn();
  const onNotice = jest.fn();
  const { result } = renderHook(() => useVoiceInput({ onTranscript, onNotice }));
  await act(async () => {
    await result.current.start();
  });
  let stopped!: Promise<void>;
  await act(async () => {
    jest.advanceTimersByTime(2000);
    stopped = result.current.stop();
    await Promise.resolve();
  });
  await act(async () => {
    await result.current.cancel();
    finish('late text');
    await stopped;
  });
  expect(onTranscript).not.toHaveBeenCalled();
  expect(onNotice).not.toHaveBeenCalled();
});

test('cap snapshots duration before deferred stop and upload complete', async () => {
  let finishStop!: () => void;
  jest.mocked(recorder.stop).mockReturnValue(
    new Promise<void>((resolve) => {
      finishStop = resolve;
    }),
  );
  const onTranscript = jest.fn();
  const onFinished = jest.fn();
  const { result } = renderHook(() =>
    useVoiceInput({ onTranscript, onNotice: jest.fn(), onFinished }),
  );
  await act(async () => {
    await result.current.start();
  });
  await act(async () => {
    jest.advanceTimersByTime(60000);
    await Promise.resolve();
  });
  expect(upload).not.toHaveBeenCalled();
  await act(async () => {
    jest.advanceTimersByTime(3000);
    finishStop();
    await Promise.resolve();
  });
  expect(onTranscript).toHaveBeenCalledWith('bought bread', 60);
  expect(onFinished).toHaveBeenCalledTimes(1);
  await act(async () => {
    await result.current.stop();
  });
  expect(recorder.stop).toHaveBeenCalledTimes(1);
});

test('cancel while native stop is pending prevents upload', async () => {
  let finish!: () => void;
  jest.mocked(recorder.stop).mockReturnValue(
    new Promise<void>((resolve) => {
      finish = resolve;
    }),
  );
  const onTranscript = jest.fn();
  const { result } = renderHook(() => useVoiceInput({ onTranscript, onNotice: jest.fn() }));
  await act(async () => {
    await result.current.start();
  });
  let stopped!: Promise<void>;
  act(() => {
    jest.advanceTimersByTime(2000);
    stopped = result.current.stop();
  });
  await act(async () => {
    await result.current.cancel();
    finish();
    await stopped;
  });
  expect(upload).not.toHaveBeenCalled();
  expect(onTranscript).not.toHaveBeenCalled();
  expect(result.current.state).toBe('idle');
});

test('recorder failure finishes the hold without a transcript', async () => {
  jest.mocked(recorder.stop).mockRejectedValue(new Error('native failure'));
  const onFinished = jest.fn();
  const onNotice = jest.fn();
  const onTranscript = jest.fn();
  const { result } = renderHook(() => useVoiceInput({ onTranscript, onNotice, onFinished }));
  await act(async () => {
    await result.current.start();
  });
  await act(async () => {
    jest.advanceTimersByTime(2000);
    await result.current.stop();
  });
  expect(onFinished).toHaveBeenCalledTimes(1);
  expect(onNotice).toHaveBeenCalledTimes(1);
  expect(onTranscript).not.toHaveBeenCalled();
  expect(result.current.state).toBe('idle');
});

test('cancelled upload keeps the session busy so a new start cannot revive its callback', async () => {
  let finish!: (text: string) => void;
  upload.mockReturnValue(
    new Promise<string>((resolve) => {
      finish = resolve;
    }),
  );
  const onTranscript = jest.fn();
  const { result } = renderHook(() => useVoiceInput({ onTranscript, onNotice: jest.fn() }));
  await act(async () => {
    await result.current.start();
  });
  let stopped!: Promise<void>;
  await act(async () => {
    jest.advanceTimersByTime(2000);
    stopped = result.current.stop();
    await Promise.resolve();
  });
  await act(async () => {
    await result.current.cancel();
    await result.current.start();
  });
  expect(recorder.record).toHaveBeenCalledTimes(1);
  await act(async () => {
    finish('stale');
    await stopped;
  });
  expect(onTranscript).not.toHaveBeenCalled();
  await act(async () => {
    await result.current.start();
  });
  expect(recorder.record).toHaveBeenCalledTimes(2);
  expect(result.current.state).toBe('recording');
});
