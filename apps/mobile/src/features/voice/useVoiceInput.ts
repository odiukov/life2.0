import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { Alert, Linking } from 'react-native';
import {
  AudioModule,
  AudioQuality,
  IOSOutputFormat,
  setAudioModeAsync,
  useAudioRecorder,
  useAudioRecorderState,
  type RecordingOptions,
} from 'expo-audio';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { uploadRecording, VoiceError } from './upload';
import { MAX_RECORDING_MS, voiceReducer } from './voiceState';

const OPTIONS: RecordingOptions = {
  isMeteringEnabled: true,
  extension: '.m4a',
  sampleRate: 16000,
  numberOfChannels: 1,
  bitRate: 32000,
  android: { outputFormat: 'mpeg4', audioEncoder: 'aac' },
  ios: { outputFormat: IOSOutputFormat.MPEG4AAC, audioQuality: AudioQuality.MEDIUM },
  web: {},
};

type Options = {
  onTranscript: (text: string, seconds: number) => void;
  onNotice: (text: string) => void;
  onFinished?: () => void;
};
type Phase = 'idle' | 'starting' | 'recording' | 'stopping' | 'transcribing';

export function useVoiceInput({ onTranscript, onNotice, onFinished }: Options) {
  const locale = appLocale();
  const t = useT(locale);
  const recorder = useAudioRecorder(OPTIONS);
  const recorderState = useAudioRecorderState(recorder, 100);
  const cancelled = useRef(false);
  const [state, dispatch] = useReducer(voiceReducer, { phase: 'idle' });
  const [seconds, setSeconds] = useState(0);
  const phase = useRef<Phase>('idle');
  const startedAt = useRef(0);
  const released = useRef(false);
  const mounted = useRef(true);
  const cap = useRef<ReturnType<typeof setTimeout> | null>(null);
  const callbacks = useRef({ onTranscript, onNotice, onFinished, t, locale });
  callbacks.current = { onTranscript, onNotice, onFinished, t, locale };

  const clearCap = useCallback(() => {
    if (cap.current !== null) clearTimeout(cap.current);
    cap.current = null;
  }, []);

  useEffect(() => {
    if (state.phase !== 'recording') return;
    const tick = setInterval(
      () => setSeconds(Math.floor((Date.now() - state.startedAt) / 1000)),
      250,
    );
    return () => clearInterval(tick);
  }, [state]);

  useEffect(
    () => () => {
      mounted.current = false;
      released.current = true;
      clearCap();
      if (phase.current === 'recording') {
        phase.current = 'stopping';
        void recorder
          .stop()
          .catch(() => undefined)
          .then(() => setAudioModeAsync({ allowsRecording: false }).catch(() => undefined));
      }
    },
    [recorder, clearCap],
  );

  const stop = useCallback(async () => {
    if (phase.current === 'starting') {
      released.current = true;
      return;
    }
    if (phase.current !== 'recording') return;
    phase.current = 'stopping';
    clearCap();
    const at = Date.now();
    const duration = Math.floor((at - startedAt.current) / 1000);
    const next = voiceReducer(
      { phase: 'recording', startedAt: startedAt.current },
      { type: 'stop', at },
    );
    dispatch({ type: 'stop', at });
    try {
      await recorder.stop();
      if (cancelled.current || !mounted.current || next.phase !== 'transcribing') return;
      phase.current = 'transcribing';
      const uri = recorder.uri;
      if (!uri) {
        callbacks.current.onNotice(callbacks.current.t('voice.not_heard'));
        return;
      }
      const text = await uploadRecording(uri, callbacks.current.locale);
      if (!mounted.current || cancelled.current) return;
      if (text.trim()) callbacks.current.onTranscript(text, duration);
      else callbacks.current.onNotice(callbacks.current.t('voice.not_heard'));
    } catch (error) {
      if (mounted.current && !cancelled.current) {
        const code = error instanceof VoiceError ? error.code : 'stt_unavailable';
        const key =
          code === 'audio_too_long'
            ? 'voice.too_long'
            : code === 'unsupported_audio'
              ? 'voice.not_heard'
              : 'voice.unavailable';
        callbacks.current.onNotice(callbacks.current.t(key));
      }
    } finally {
      await setAudioModeAsync({ allowsRecording: false }).catch(() => undefined);
      phase.current = 'idle';
      if (mounted.current) {
        dispatch({ type: 'done' });
        setSeconds(0);
        callbacks.current.onFinished?.();
      }
    }
  }, [recorder, clearCap]);

  const start = useCallback(async () => {
    if (!mounted.current || phase.current !== 'idle') return;
    cancelled.current = false;
    phase.current = 'starting';
    released.current = false;
    let prepared = false;
    try {
      const permission = await AudioModule.requestRecordingPermissionsAsync();
      if (!mounted.current || released.current) return;
      if (!permission.granted) {
        Alert.alert(
          callbacks.current.t('voice.permission_title'),
          callbacks.current.t('voice.permission_body'),
          [
            { text: callbacks.current.t('voice.cancel'), style: 'cancel' },
            {
              text: callbacks.current.t('voice.open_settings'),
              onPress: () => void Linking.openSettings(),
            },
          ],
        );
        return;
      }
      await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
      if (!mounted.current || released.current) return;
      await recorder.prepareToRecordAsync();
      prepared = true;
      // A finger may have been released while native preparation was pending.
      if (!mounted.current || released.current) return;
      recorder.record();
      phase.current = 'recording';
      startedAt.current = Date.now();
      dispatch({ type: 'start', at: startedAt.current });
      cap.current = setTimeout(() => {
        void stop();
      }, MAX_RECORDING_MS);
    } catch {
      if (mounted.current) callbacks.current.onNotice(callbacks.current.t('voice.unavailable'));
    } finally {
      if (phase.current === 'starting') {
        if (prepared) {
          // Release a prepared native recorder even when no audio was captured.
          await recorder.stop().catch(() => undefined);
        }
        await setAudioModeAsync({ allowsRecording: false }).catch(() => undefined);
        phase.current = 'idle';
        if (mounted.current) callbacks.current.onFinished?.();
      }
    }
  }, [recorder, stop]);

  const cancel = useCallback(async () => {
    cancelled.current = true;
    await stop();
  }, [stop]);

  return {
    state: state.phase,
    seconds,
    level: state.phase === 'recording' ? meteringLevel(recorderState.metering) : 0,
    start,
    stop,
    cancel,
  };
}

/** Convert dBFS metering to a visual level; -60 dB and below is silence. */
export function meteringLevel(db: number | null | undefined): number {
  if (db == null || !Number.isFinite(db)) return 0;
  return Math.min(1, Math.max(0, (db + 60) / 60));
}
