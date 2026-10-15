import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, BackHandler, Dimensions, Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withTiming,
} from 'react-native-reanimated';
import { GestureDetector } from 'react-native-gesture-handler';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { useSheetAnimation } from '@/lib/sheetAnimation';
import { useSwipeToDismiss } from '@/lib/useSwipeToDismiss';
import { TaskBusyError, TasksApiError } from '@/features/chat/tasksApi';
import { useTask } from '@/features/chat/useTask';
import { useTaskSheet, type OpenRequest } from './sheetStore';
import { TaskConversation, type Seed, type VoiceNote } from './TaskConversation';
import { BUTTON_SIZE } from './TaskButton';

const { width: W, height: H } = Dimensions.get('window');
const SHEET_TOP = Math.round(H * 0.08); // the sheet covers 92 % of the screen
const BLOOM_MS = 280;
const BACKDROP_COLOR = 'rgba(0,0,0,0.6)';

export function TaskSheet() {
  const t = useT(appLocale());
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const visible = useTaskSheet((s) => s.visible);
  const origin = useTaskSheet((s) => s.origin);
  const pending = useTaskSheet((s) => s.pending);
  const chat = useTask();
  const chatRef = useRef(chat);
  chatRef.current = chat;
  const [seed, setSeed] = useState<Seed | undefined>(undefined);
  const [voiceNotes, setVoiceNotes] = useState<VoiceNote[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [restored, setRestored] = useState(false);
  const [restoreFailed, setRestoreFailed] = useState(false);
  const [requestFailed, setRequestFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  const applying = useRef(false);
  const closing = useRef(false);
  const epoch = useRef(0);
  const restoreRunning = useRef(false);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reduceMotion = useReducedMotion();

  const hasContent =
    !restored ||
    chat.phase !== 'idle' ||
    applying.current ||
    chat.taskId !== null ||
    chat.messages.length > 0;
  const blocked = useSharedValue(false);
  useEffect(() => {
    blocked.value = hasContent;
  }, [hasContent, blocked]);

  const flash = useCallback((message: string) => {
    setNotice(message);
    if (noticeTimer.current) clearTimeout(noticeTimer.current);
    noticeTimer.current = setTimeout(() => setNotice(null), 3000);
  }, []);
  useEffect(
    () => () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    },
    [],
  );

  const restore = useCallback(async () => {
    if (restoreRunning.current) return;
    restoreRunning.current = true;
    const version = epoch.current;
    setRestoreFailed(false);
    try {
      await chatRef.current.restore();
      if (version !== epoch.current) return;
      setRestored(true);
      if (chatRef.current.taskId) useTaskSheet.getState().show();
    } catch {
      if (version !== epoch.current) return;
      setRestoreFailed(true);
      useTaskSheet.getState().show();
    } finally {
      restoreRunning.current = false;
    }
  }, []);
  useEffect(() => {
    void restore();
  }, [restore]);
  useEffect(() => {
    if (restored && chat.taskId) useTaskSheet.getState().show();
  }, [restored, chat.taskId]);

  const apply = useCallback(
    async (req: OpenRequest, version: number) => {
      const c = chatRef.current;
      try {
        if (req.lead) await c.setLead(req.lead);
        if (closing.current || version !== epoch.current) return false;
        if (req.voice) {
          const note = req.voice;
          if (!(await c.send({ text: note.text }))) return false;
          if (version !== epoch.current) return false;
          setVoiceNotes((v) => [...v, note]);
        } else if (req.send) {
          if (!(await c.send({ text: req.send }))) return false;
        }
        if (version !== epoch.current) return false;
        if (req.prefill !== undefined || req.attachments?.length) {
          setSeed((s) => ({
            key: (s?.key ?? 0) + 1,
            text: req.prefill,
            attachments: req.attachments,
          }));
        }
        return true;
      } catch (e) {
        flash(
          e instanceof TasksApiError && e.code === 'no_household'
            ? t('task.no_household')
            : t('chat.client.generic'),
        );
        return false;
      }
    },
    [flash, t],
  );

  // Keep the head queued until its send completes; a busy stream cannot consume it.
  useEffect(() => {
    if (
      !visible ||
      !pending ||
      !restored ||
      requestFailed ||
      closing.current ||
      applying.current ||
      chat.phase !== 'idle'
    )
      return;
    applying.current = true;
    const version = epoch.current;
    void apply(pending, version)
      .then((accepted) => {
        if (version !== epoch.current) return;
        if (accepted && useTaskSheet.getState().pending === pending) useTaskSheet.getState().take();
        else setRequestFailed(true);
      })
      .finally(() => {
        applying.current = false;
        setRevision((r) => r + 1);
      });
  }, [visible, pending, restored, requestFailed, chat.phase, revision, apply]);

  const hide = useCallback(() => {
    epoch.current += 1;
    setVoiceNotes([]);
    setSeed(undefined);
    setNotice(null);
    setRequestFailed(false);
    setRevision((r) => r + 1);
    useTaskSheet.getState().hide();
  }, []);

  const end = useCallback(async () => {
    closing.current = true;
    epoch.current += 1;
    try {
      await chatRef.current.close();
      setRestored(true);
      setRestoreFailed(false);
      setVoiceNotes([]);
      setSeed(undefined);
      hide();
    } catch (e) {
      if (useTaskSheet.getState().pending) setRequestFailed(true);
      if (e instanceof TaskBusyError) flash(t('task.close.busy'));
      else flash(t('chat.client.generic'));
    } finally {
      closing.current = false;
      setRevision((r) => r + 1);
    }
  }, [flash, hide, t]);

  const requestClose = useCallback(() => {
    if (
      restored &&
      !applying.current &&
      chatRef.current.phase === 'idle' &&
      !(chatRef.current.taskId !== null || chatRef.current.messages.length > 0)
    ) {
      hide();
      return;
    }
    Alert.alert(t('task.close.title'), t('task.close.body'), [
      { text: t('task.close.continue'), style: 'cancel' },
      { text: t('task.close.end'), style: 'destructive', onPress: () => void end() },
    ]);
  }, [end, hide, restored, t]);
  useEffect(() => {
    if (!visible) return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => {
      requestClose();
      return true;
    });
    return () => subscription.remove();
  }, [visible, requestClose]);

  const { mounted, sheetY, backdropAlpha, backdropStyle, sheetStyle } = useSheetAnimation(visible);
  const { panGesture } = useSwipeToDismiss({
    sheetY,
    backdropAlpha,
    onClose: hide,
    ignoreScroll: true,
    dismissBlocked: blocked,
    onDismissBlocked: requestClose,
  });

  const bloom = useSharedValue(1);
  useEffect(() => {
    if (!visible || reduceMotion) return;
    bloom.value = 0;
    bloom.value = withTiming(1, { duration: BLOOM_MS, easing: Easing.out(Easing.cubic) });
  }, [visible, reduceMotion, bloom]);
  const cx = origin?.x ?? W / 2;
  const cy = origin?.y ?? H - 60;
  const maxScale = (2 * Math.hypot(Math.max(cx, W - cx), Math.max(cy, H - cy))) / BUTTON_SIZE;
  const bloomStyle = useAnimatedStyle(() => ({
    opacity: 1 - bloom.value,
    transform: [{ scale: 1 + bloom.value * (maxScale - 1) }],
  }));

  if (!mounted) return null;

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="box-none">
      <Animated.View
        style={[StyleSheet.absoluteFill, styles.backdrop, backdropStyle]}
        pointerEvents="none"
      />
      <Pressable
        style={[StyleSheet.absoluteFill, { bottom: H - SHEET_TOP }]}
        onPress={requestClose}
        accessibilityElementsHidden
      />
      {!reduceMotion && (
        <Animated.View
          pointerEvents="none"
          style={[
            {
              position: 'absolute',
              left: cx - BUTTON_SIZE / 2,
              top: cy - BUTTON_SIZE / 2,
              width: BUTTON_SIZE,
              height: BUTTON_SIZE,
              borderRadius: BUTTON_SIZE / 2,
              backgroundColor: colors.accent,
            },
            bloomStyle,
          ]}
        />
      )}
      <Animated.View
        testID="task-sheet"
        style={[
          styles.sheet,
          { top: SHEET_TOP, backgroundColor: colors.bg1, paddingBottom: insets.bottom },
          sheetStyle,
        ]}
      >
        <GestureDetector gesture={panGesture}>
          <View style={styles.grab}>
            <View style={[styles.handle, { backgroundColor: colors.bg3 }]} />
          </View>
        </GestureDetector>
        {!restored && (
          <Pressable testID="task-restore-close" onPress={requestClose}>
            <Text>{t('task.close.end')}</Text>
          </Pressable>
        )}
        {restoreFailed && (
          <View>
            <Text>{t('task.restore_failed')}</Text>
            <Pressable accessibilityRole="button" onPress={() => void restore()}>
              <Text>{t('task.sheet_retry')}</Text>
            </Pressable>
          </View>
        )}
        {requestFailed && (
          <Pressable accessibilityRole="button" onPress={() => setRequestFailed(false)}>
            <Text>{t('task.sheet_retry')}</Text>
          </Pressable>
        )}
        {restored && visible && (
          <TaskConversation
            chat={chat}
            seed={seed}
            voiceNotes={voiceNotes}
            onClose={requestClose}
            keyboardOffset={SHEET_TOP}
            autoFocus={visible && voiceNotes.length === 0 && chat.messages.length === 0}
          />
        )}
        {notice && (
          <Text style={[styles.notice, { color: colors.fg2, backgroundColor: colors.bg3 }]}>
            {notice}
          </Text>
        )}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: { backgroundColor: BACKDROP_COLOR },
  grab: { alignItems: 'center', height: 22, justifyContent: 'center' },
  handle: { borderRadius: 2, height: 4, width: 36 },
  notice: {
    alignSelf: 'center',
    borderRadius: 12,
    bottom: 96,
    fontSize: 13,
    overflow: 'hidden',
    paddingHorizontal: 12,
    paddingVertical: 8,
    position: 'absolute',
  },
  sheet: {
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    bottom: 0,
    left: 0,
    overflow: 'hidden',
    position: 'absolute',
    right: 0,
  },
});
