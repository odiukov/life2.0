import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { FlatList, Keyboard, Text, View } from 'react-native';
import { KeyboardAvoidingView } from 'react-native-keyboard-controller';
import { useBottomTabBarHeight } from '@react-navigation/bottom-tabs';
import {
  AgentHeader,
  AskBar,
  Bubble,
  Screen,
  useTheme,
  type AgentId,
  type AskBarHandle,
} from '@life-agents/ui';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';
import * as Linking from 'expo-linking';
import { useTask, type ChatMessage } from './useTask';
import { ActionCard } from './ActionCard';
import { ErrorBubble } from './ErrorBubble';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { ChatHeader } from './ChatHeader';
import { CommandPalette } from './CommandPalette';
import { matchCommands, splitLeadingTag } from './commands';
import { useConnectedIntegrations } from '../integrations/store';
import { blockedAgents } from './agentRequirements';
import { isAgentId } from '../agents/agentStatusRules';
import { FilePreviewChip } from './FilePreviewChip';
import { consumePendingShareUrl } from './pendingShare';
import { parseAgentTags } from './parseAgentTags';
import { useVoiceInput } from '../voice/useVoiceInput';
import { mergeTranscript } from '../voice/voiceState';

type PendingFile = { uri: string; name: string; size: number };
type SendInput = { tag?: AgentId; text: string };

export function ChatScreen() {
  const chat = useTask();
  const { messages, send: sendMessage, restore, startNew, setLead } = chat;
  const t = useT(appLocale());
  const [taskNotice, setTaskNotice] = useState<string | null>(null);
  const clientError = (code: string) => {
    const key = `chat.client.${code}`;
    const translated = t(key);
    return translated === key ? t('chat.client.generic') : translated;
  };
  const restored = useRef<Promise<void> | null>(null);
  useEffect(() => {
    restored.current ??= restore().catch(() => setTaskNotice(t('chat.client.network')));
  }, [restore, t]);
  const resetThread = useCallback(async () => {
    try {
      await startNew();
      setTaskNotice(t('chat.client.new_task'));
      setDraft({ text: '' });
    } catch {
      setTaskNotice(t('chat.client.close_failed'));
    }
  }, [startNew, t]);
  const { spacing, colors } = useTheme();
  const router = useRouter();
  const tabBarHeight = useBottomTabBarHeight();
  const [draft, setDraft] = useState<{ tag?: AgentId; text: string }>({ tag: undefined, text: '' });
  const [pendingFile, setPendingFile] = useState<PendingFile | null>(null);
  const [voiceNotice, setVoiceNotice] = useState<string | null>(null);
  const noticeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voice = useVoiceInput({
    onTranscript: (text) =>
      setDraft((current) => ({ ...current, text: mergeTranscript(current.text, text) })),
    onNotice: (text) => {
      setVoiceNotice(text);
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
      noticeTimer.current = setTimeout(() => setVoiceNotice(null), 3000);
    },
  });
  useEffect(
    () => () => {
      if (noticeTimer.current) clearTimeout(noticeTimer.current);
    },
    [],
  );
  const connected = useConnectedIntegrations();
  const blocked = useMemo(() => blockedAgents(connected), [connected]);
  const commandMatches = matchCommands(draft.text, connected);
  const {
    prefill,
    send: autoSend,
    tag,
  } = useLocalSearchParams<{
    prefill?: string;
    send?: string;
    tag?: string;
  }>();
  const listRef = useRef<FlatList>(null);
  const askBarRef = useRef<AskBarHandle>(null);
  const submitted = useRef(false);

  useEffect(() => {
    const id = setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
    return () => clearTimeout(id);
  }, [messages.length]);

  useFocusEffect(
    useCallback(() => {
      if (autoSend) {
        void (restored.current ?? Promise.resolve()).then(async () => {
          if (autoSend.trim() === '/new') return resetThread();
          const input = splitLeadingTag(autoSend);
          if (!(await sendMessage({ ...input, attachments: [] }))) setDraft(input);
        });
        router.setParams({ send: undefined });
      } else if (prefill !== undefined || tag) {
        const safeTag = isAgentId(tag) ? tag : undefined;
        setDraft({ tag: safeTag, text: prefill ?? '' });
        router.setParams({ prefill: undefined, tag: undefined });
        // Mirror the focus-after-animation timing used by the previous
        // ChatHeader.onPrefill callback so the keyboard opens reliably.
        setTimeout(() => askBarRef.current?.focus(), 250);
      }
    }, [autoSend, prefill, tag, router, sendMessage, resetThread]),
  );

  const applyShareUrl = useCallback((url: string) => {
    const { queryParams } = Linking.parse(url);
    const fileURL = queryParams?.shareFileURL as string | undefined;
    const fileName = queryParams?.shareFileName as string | undefined;
    if (fileURL && fileName)
      setPendingFile({
        uri: fileURL,
        name: fileName,
        size: Number(queryParams?.shareFileSize) || 0,
      });
  }, []);

  useFocusEffect(
    useCallback(() => {
      const url = consumePendingShareUrl();
      if (url) applyShareUrl(url);
    }, [applyShareUrl]),
  );

  useEffect(() => {
    const sub = Linking.addEventListener('url', ({ url }) => applyShareUrl(url));
    return () => sub.remove();
  }, [applyShareUrl]);

  const handleAttach = useCallback(async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: 'application/pdf',
      copyToCacheDirectory: true,
    });
    const asset = result.assets?.[0];
    if (result.canceled || !asset) return;
    setPendingFile({ uri: asset.uri, name: asset.name, size: asset.size ?? 0 });
  }, []);

  const handleSend = useCallback(
    async (next: SendInput) => {
      Keyboard.dismiss();
      submitted.current = true;
      if (next.text.trim() === '/new') {
        await resetThread();
        return;
      }
      const input = next.tag ? next : splitLeadingTag(next.text);
      setTaskNotice(null);
      // AskBar emits an empty draft after onSubmit; retain input until accepted.
      setDraft(next);
      try {
        if (input.tag && !input.text.trim() && !pendingFile) {
          await setLead(input.tag);
          return;
        }
        const sent = await sendMessage({
          ...input,
          attachments: pendingFile ? [{ ...pendingFile, mime: 'application/pdf' }] : [],
        });
        if (sent) {
          setPendingFile(null);
          setDraft({ tag: undefined, text: '' });
        }
      } catch {
        setTaskNotice(t('chat.client.network'));
      }
    },
    [pendingFile, sendMessage, resetThread, setLead, t],
  );

  return (
    <Screen edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior="padding"
        keyboardVerticalOffset={tabBarHeight}
      >
        <ChatHeader />
        <FlatList<ChatMessage>
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{ padding: spacing.s3, gap: spacing.s2 }}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          renderItem={({ item }) =>
            item.kind === 'error' ? (
              <ErrorBubble message={item.message || clientError(item.code)} />
            ) : item.kind === 'user' ? (
              <View>
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
                  item.id === messages.filter((m) => m.kind === 'user').at(-1)?.id && (
                    <Text style={{ color: colors.fg3 }}>{t('chat.client.reply_missing')}</Text>
                  )}
              </View>
            ) : (
              <View style={{ gap: spacing.s1, alignItems: 'flex-start' }}>
                {item.agent && (
                  <AgentHeader primary={item.agent} consulted={item.consulted ?? []} />
                )}
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
        {commandMatches.length > 0 && !draft.tag && (
          <CommandPalette
            items={commandMatches}
            onSelect={(c) => {
              if (c.name === '/new') {
                resetThread();
                setDraft({ tag: undefined, text: '' });
                Keyboard.dismiss();
                return;
              }
              setDraft({ tag: c.agent, text: '' });
              void setLead(c.agent).catch(() => setTaskNotice(t('chat.client.network')));
            }}
          />
        )}
        {pendingFile && (
          <FilePreviewChip fileName={pendingFile.name} onDismiss={() => setPendingFile(null)} />
        )}
        {taskNotice && <Text style={{ color: colors.fg3, textAlign: 'center' }}>{taskNotice}</Text>}
        {voiceNotice && (
          <Text style={{ color: colors.fg3, textAlign: 'center', marginBottom: 4 }}>
            {voiceNotice}
          </Text>
        )}
        <AskBar
          ref={askBarRef}
          value={draft.text}
          tag={draft.tag ?? chat.leadAgent ?? undefined}
          onChangeText={(next) => {
            if (submitted.current) {
              submitted.current = false;
              return;
            }
            if (!next.tag && (draft.tag || chat.leadAgent))
              void setLead(null).catch(() => setTaskNotice(t('chat.client.network')));
            submitted.current = false;
            setDraft(next);
          }}
          onSubmit={handleSend}
          onAttach={handleAttach}
          onVoiceStart={() => {
            void voice.start();
          }}
          onVoiceEnd={() => {
            void voice.stop();
          }}
          voiceState={voice.state}
          recordingSeconds={voice.seconds}
          hasAttachment={!!pendingFile}
          disabled={chat.phase !== 'idle'}
          blockedAgents={blocked}
        />
      </KeyboardAvoidingView>
    </Screen>
  );
}
