import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActionSheetIOS, // eslint-disable-line react-native/split-platform-components -- guarded by Platform.OS
  Alert,
  FlatList,
  Keyboard,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  Text,
  View,
} from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import {
  AgentHeader,
  AskBar,
  Bubble,
  Icon,
  useTheme,
  type AgentId,
  type AskBarHandle,
} from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import type { OutgoingAttachment } from '@/features/chat/tasksApi';
import type { ChatMessage, useTask } from '@/features/chat/useTask';
import { ActionCard } from '@/features/chat/ActionCard';
import { ErrorBubble } from '@/features/chat/ErrorBubble';
import { CommandPalette } from '@/features/chat/CommandPalette';
import { FilePreviewChip } from '@/features/chat/FilePreviewChip';
import { matchCommands, splitLeadingTag } from '@/features/chat/commands';
import { blockedAgents } from '@/features/chat/agentRequirements';
import { parseAgentTags } from '@/features/chat/parseAgentTags';
import { useConnectedIntegrations } from '../integrations/store';
import { useVoiceInput } from '../voice/useVoiceInput';
import {
  CameraDenied,
  LIMITS,
  pickAttachments,
  validateAttachments,
  type Source,
} from './attachments';
import { quickLeads } from './quickChips';
import { LeadChip } from './LeadChip';

export type TaskChat = ReturnType<typeof useTask>;
export type Seed = { key: number; text?: string; attachments?: OutgoingAttachment[] };
export type VoiceNote = { text: string; seconds: number };

type Props = {
  chat: TaskChat;
  seed?: Seed;
  voiceNotes?: VoiceNote[];
  onClose?: () => void;
  keyboardOffset?: number;
  autoFocus?: boolean;
};

const mmss = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;

export function TaskConversation({
  chat,
  seed,
  voiceNotes = [],
  onClose,
  keyboardOffset = 0,
  autoFocus,
}: Props) {
  const t = useT(appLocale());
  const { colors, spacing } = useTheme();
  const connected = useConnectedIntegrations();
  const blocked = useMemo(() => blockedAgents(connected), [connected]);
  const [text, setText] = useState('');
  const textRef = useRef(text);
  textRef.current = text;
  const [attachments, setAttachments] = useState<OutgoingAttachment[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const askBarRef = useRef<AskBarHandle>(null);
  const listRef = useRef<FlatList>(null);
  const attachmentsRef = useRef(attachments);
  attachmentsRef.current = attachments;

  const notify = useCallback((message: string) => {
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

  useEffect(() => {
    if (!seed) return;
    if (seed.attachments?.length) {
      const merged = [...attachmentsRef.current, ...seed.attachments];
      const check = validateAttachments(merged);
      if (!check.ok) {
        notify(t(`task.attach.${check.reason}`));
        return;
      }
      setAttachments(merged);
    }
    if (seed.text !== undefined) setText(seed.text);
    if (autoFocus || seed.text !== undefined) setTimeout(() => askBarRef.current?.focus(), 250);
  }, [seed?.key]);

  useEffect(() => {
    if (autoFocus) setTimeout(() => askBarRef.current?.focus(), 250);
  }, [autoFocus]);

  const retryInput = useRef<{
    text: string;
    tag?: AgentId;
    attachments: OutgoingAttachment[];
  } | null>(null);
  const [retry, setRetry] = useState(false);
  const submit = useCallback(
    async (input: { text: string; tag?: AgentId; attachments?: OutgoingAttachment[] }) => {
      const files = input.attachments ?? attachmentsRef.current;
      const check = validateAttachments(files);
      if (!check.ok) {
        notify(t(`task.attach.${check.reason}`));
        return false;
      }
      const outgoing = { ...input, attachments: files };
      retryInput.current = outgoing;
      Keyboard.dismiss();
      try {
        const sent = await chat.send(outgoing);
        if (sent) {
          setText((current) => {
            const parsed = splitLeadingTag(current.trim());
            return parsed.text === input.text && parsed.tag === input.tag ? '' : current;
          });
          setAttachments((current) => (current === files ? [] : current));
          setRetry(false);
        } else {
          setText((current) => current || input.text);
          setRetry(true);
          notify(t('chat.client.network'));
        }
        return sent;
      } catch {
        setText((current) => current || input.text);
        setRetry(true);
        notify(t('chat.client.network'));
        return false;
      }
    },
    [chat, notify, t],
  );
  const changeLead = (lead: AgentId | null) => {
    void chat.setLead(lead).catch(() => notify(t('chat.client.network')));
  };

  const voice = useVoiceInput({
    onTranscript: (spoken) => {
      submit({ text: spoken });
    },
    onNotice: notify,
  });

  const handleSubmit = useCallback(
    async (next: { tag?: AgentId; text: string }) => {
      const parsed = next.tag ? next : splitLeadingTag(next.text);
      if (parsed.tag && !parsed.text.trim() && attachmentsRef.current.length === 0) {
        const draft = textRef.current;
        try {
          await chat.setLead(parsed.tag);
          setText((current) => (current === draft ? '' : current));
        } catch {
          notify(t('chat.client.network'));
        }
        return;
      }
      await submit(parsed.tag ? { text: parsed.text, tag: parsed.tag } : { text: parsed.text });
    },
    [chat, notify, submit, t],
  );

  const chooseSource = useCallback(
    () =>
      new Promise<Source | null>((resolve) => {
        const sources: Source[] = ['camera', 'gallery', 'file'];
        const labels = [t('task.attach.camera'), t('task.attach.gallery'), t('task.attach.file')];
        if (Platform.OS === 'ios') {
          ActionSheetIOS.showActionSheetWithOptions(
            {
              options: [...labels, t('task.attach.cancel')],
              cancelButtonIndex: 3,
              title: t('task.attach.title'),
            },
            (i) => resolve(sources[i] ?? null),
          );
        } else {
          Alert.alert(
            t('task.attach.title'),
            undefined,
            labels.map((label, i) => ({ text: label, onPress: () => resolve(sources[i]!) })),
            { cancelable: true, onDismiss: () => resolve(null) },
          );
        }
      }),
    [t],
  );

  const handleAttach = useCallback(async () => {
    const source = await chooseSource();
    if (!source) return;
    try {
      if (attachmentsRef.current.length >= LIMITS.count) {
        notify(t('task.attach.too_many'));
        return;
      }
      const picked = await pickAttachments(source, LIMITS.count - attachmentsRef.current.length);
      if (picked.length) {
        const merged = [...attachmentsRef.current, ...picked];
        const check = validateAttachments(merged);
        if (check.ok) setAttachments(merged);
        else notify(t(`task.attach.${check.reason}`));
      }
    } catch (e) {
      if (e instanceof CameraDenied) {
        Alert.alert(t('task.attach.camera_denied'), undefined, [
          { text: t('task.attach.cancel'), style: 'cancel' },
          { text: t('voice.open_settings'), onPress: () => void Linking.openSettings() },
        ]);
      } else notify(t('chat.client.network'));
    }
  }, [chooseSource, notify, t]);

  const commandMatches = matchCommands(text, connected);
  const clientError = (code: string) => {
    if (code === 'no_household') return t('task.no_household');
    const key = `chat.client.${code}`;
    const value = t(key);
    return value === key ? t('chat.client.generic') : value;
  };
  const empty = chat.messages.length === 0;
  const noteFor = (msgText: string) => voiceNotes.find((n) => n.text === msgText);

  return (
    <KeyboardAvoidingView
      style={{ flex: 1 }}
      behavior="padding"
      keyboardVerticalOffset={keyboardOffset}
    >
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: spacing.s2,
          paddingHorizontal: spacing.s3,
          paddingVertical: spacing.s2,
          borderBottomWidth: 1,
          borderBottomColor: colors.borderSoft,
        }}
      >
        <Text style={{ flex: 1, color: colors.fg1, fontSize: 15, fontWeight: '600' }}>
          {t('task.title')}
        </Text>
        {chat.leadAgent && <LeadChip agent={chat.leadAgent} onClear={() => changeLead(null)} />}
        {onClose && (
          <Pressable
            testID="task-close"
            onPress={onClose}
            hitSlop={10}
            accessibilityRole="button"
            accessibilityLabel={t('task.close.end')}
            style={{
              width: 28,
              height: 28,
              borderRadius: 14,
              backgroundColor: colors.bg3,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Icon name="X" size={13} color={colors.fg2} />
          </Pressable>
        )}
      </View>
      <FlatList<ChatMessage>
        ref={listRef}
        data={chat.messages}
        keyExtractor={(m) => m.id}
        contentContainerStyle={{ padding: spacing.s3, gap: spacing.s2 }}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        renderItem={({ item }) =>
          item.kind === 'error' ? (
            <View>
              <ErrorBubble message={item.message || clientError(item.code)} />
              {item.id === chat.messages.at(-1)?.id &&
                ['network', 'task_busy'].includes(item.code) && (
                  <Pressable
                    onPress={() => {
                      const last = [...chat.messages].reverse().find((m) => m.kind === 'user');
                      const input =
                        retryInput.current ??
                        (last?.kind === 'user'
                          ? { text: last.text, tag: last.tag, attachments: [] }
                          : null);
                      if (input) void submit(input);
                    }}
                  >
                    <Text>{t('task.retry')}</Text>
                  </Pressable>
                )}
            </View>
          ) : item.kind === 'user' ? (
            <View>
              {noteFor(item.text) && (
                <Text style={{ alignSelf: 'flex-end', color: colors.fg3 }}>
                  {t('task.voice_note', { duration: mmss(noteFor(item.text)!.seconds) })}
                </Text>
              )}
              <Bubble
                variant="user"
                segments={[
                  ...(item.tag
                    ? [{ tag: item.tag } as const, ` ${item.text}`]
                    : parseAgentTags(item.text)),
                  ...(item.attachments ?? []).map((a) => `\n📎 ${a.name}`),
                ]}
              />
              {chat.interrupted &&
                item.id === chat.messages.filter((m) => m.kind === 'user').at(-1)?.id && (
                  <Text style={{ color: colors.fg3 }}>{t('chat.client.reply_missing')}</Text>
                )}
            </View>
          ) : (
            <View
              testID={
                item.completed &&
                !item.streaming &&
                item.text.trim() &&
                chat.phase === 'idle' &&
                item.id === chat.messages.at(-1)?.id
                  ? 'task-assistant-complete'
                  : undefined
              }
              accessibilityLabel={
                item.completed &&
                !item.streaming &&
                item.text.trim() &&
                chat.phase === 'idle' &&
                item.id === chat.messages.at(-1)?.id
                  ? item.text
                  : undefined
              }
              style={{ gap: spacing.s1, alignItems: 'flex-start' }}
            >
              {item.agent && <AgentHeader primary={item.agent} consulted={item.consulted ?? []} />}
              {(item.text || item.streaming) && (
                <Bubble
                  variant="assistant"
                  loading={item.streaming && !item.text}
                  segments={item.text ? parseAgentTags(item.text) : undefined}
                />
              )}
              {item.action && (
                <ActionCard
                  action={item.action}
                  onConfirm={() => chat.confirm(item.action!.id)}
                  onReject={() => chat.reject(item.action!.id)}
                />
              )}
            </View>
          )
        }
      />
      {empty && !text && (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          keyboardShouldPersistTaps="always"
          contentContainerStyle={{
            gap: spacing.s2,
            paddingHorizontal: spacing.s3,
            paddingBottom: spacing.s2,
          }}
        >
          {quickLeads(connected).map((lead) => (
            <Pressable
              key={lead}
              onPress={() => {
                changeLead(lead);
                askBarRef.current?.focus();
              }}
              style={{
                paddingVertical: 7,
                paddingHorizontal: 12,
                borderRadius: 999,
                backgroundColor: chat.leadAgent === lead ? colors.accentSoft : colors.bg2,
                borderWidth: 1,
                borderColor: colors.borderSoft,
              }}
            >
              <Text style={{ color: colors.fg1, fontSize: 13 }}>{t(`task.chip.${lead}`)}</Text>
            </Pressable>
          ))}
        </ScrollView>
      )}
      {commandMatches.length > 0 && (
        <CommandPalette
          items={commandMatches}
          onSelect={(c) => {
            changeLead(c.agent);
            setText('');
          }}
        />
      )}
      {attachments.map((a, i) => (
        <FilePreviewChip
          key={`${a.uri}-${i}`}
          fileName={a.name}
          onDismiss={() => setAttachments((all) => all.filter((_, j) => j !== i))}
        />
      ))}
      {retry &&
        !['network', 'task_busy'].includes(
          chat.messages.at(-1)?.kind === 'error'
            ? (chat.messages.at(-1) as Extract<ChatMessage, { kind: 'error' }>).code
            : '',
        ) && (
          <Pressable
            onPress={() => {
              if (retryInput.current) void submit(retryInput.current);
            }}
          >
            <Text>{t('task.retry')}</Text>
          </Pressable>
        )}
      {notice && (
        <Text style={{ color: colors.fg3, textAlign: 'center', marginBottom: 4 }}>{notice}</Text>
      )}
      <AskBar
        ref={askBarRef}
        value={text}
        onChangeText={(next) => setText(next.tag ? `/${next.tag} ${next.text}` : next.text)}
        clearOnSubmit={false}
        promoteTags={false}
        onSubmit={handleSubmit}
        onAttach={() => void handleAttach()}
        onVoiceStart={() => void voice.start()}
        onVoiceEnd={() => void voice.stop()}
        voiceState={voice.state}
        recordingSeconds={voice.seconds}
        hasAttachment={attachments.length > 0}
        disabled={chat.phase !== 'idle'}
        blockedAgents={blocked}
      />
    </KeyboardAvoidingView>
  );
}
