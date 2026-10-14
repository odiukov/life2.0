export const AudioQuality = { MEDIUM: 64 };
export const IOSOutputFormat = { MPEG4AAC: 'aac ' };
export const AudioModule = {
  requestRecordingPermissionsAsync: jest.fn(async () => ({ granted: true })),
};
export const setAudioModeAsync = jest.fn(async () => undefined);
const recorder = {
  prepareToRecordAsync: jest.fn(async () => undefined),
  record: jest.fn(),
  stop: jest.fn(async () => undefined),
  uri: 'file:///tmp/voice.m4a',
};
export const useAudioRecorder = () => recorder;
