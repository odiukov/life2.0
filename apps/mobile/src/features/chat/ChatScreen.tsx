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
import { useChat, type SendInput } from './useChat';
import { ChatHeader } from './ChatHeader';
import { CommandPalette } from './CommandPalette';
import { matchCommands } from './commands';
import { useConnectedIntegrations } from '../integrations/store';
import { blockedAgents } from './agentRequirements';
import { isAgentId } from '../agents/agentStatusRules';
import { FilePreviewChip } from './FilePreviewChip';
import { consumePendingShareUrl } from './pendingShare';
import { parseAgentTags } from './parseAgentTags';
import { useVoiceInput } from '../voice/useVoiceInput';
import { mergeTranscript } from '../voice/voiceState';

type PendingFile = { uri: string; name: string };

export function ChatScreen() {
  const { messages, send: sendMessage, sendFile, resetThread } = useChat();
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

  const isStreaming = useMemo(
    () => messages.some((m) => m.kind === 'assistant' && m.streaming),
    [messages],
  );

  useEffect(() => {
    const id = setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
    return () => clearTimeout(id);
  }, [messages.length]);

  useFocusEffect(
    useCallback(() => {
      if (autoSend) {
        sendMessage(autoSend);
        router.setParams({ send: undefined });
      } else if (prefill !== undefined || tag) {
        const safeTag = isAgentId(tag) ? tag : undefined;
        setDraft({ tag: safeTag, text: prefill ?? '' });
        router.setParams({ prefill: undefined, tag: undefined });
        // Mirror the focus-after-animation timing used by the previous
        // ChatHeader.onPrefill callback so the keyboard opens reliably.
        setTimeout(() => askBarRef.current?.focus(), 250);
      }
    }, [autoSend, prefill, tag, router, sendMessage]),
  );

  const applyShareUrl = useCallback((url: string) => {
    const { queryParams } = Linking.parse(url);
    const fileURL = queryParams?.shareFileURL as string | undefined;
    const fileName = queryParams?.shareFileName as string | undefined;
    if (fileURL && fileName) setPendingFile({ uri: fileURL, name: fileName });
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
    setPendingFile({ uri: asset.uri, name: asset.name });
  }, []);

  const handleSend = useCallback(
    (next: SendInput) => {
      Keyboard.dismiss();
      if (pendingFile) {
        const hint = next.tag;
        sendFile(pendingFile.uri, pendingFile.name, hint);
        setPendingFile(null);
      } else {
        sendMessage(next);
      }
      setDraft({ tag: undefined, text: '' });
    },
    [pendingFile, sendFile, sendMessage],
  );

  return (
    <Screen edges={['top']}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior="padding"
        keyboardVerticalOffset={tabBarHeight}
      >
        <ChatHeader />
        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{ padding: spacing.s3, gap: spacing.s2 }}
          onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
          renderItem={({ item }) =>
            item.kind === 'user' ? (
              <Bubble
                variant="user"
                segments={
                  item.tag
                    ? [{ tag: item.tag } as const, ` ${item.text}`]
                    : parseAgentTags(item.text)
                }
              />
            ) : (
              <View style={{ gap: spacing.s1, alignItems: 'flex-start' }}>
                {item.agent && (
                  <AgentHeader primary={item.agent} consulted={item.consulted ?? []} />
                )}
                <Bubble
                  variant="assistant"
                  loading={item.streaming && !item.text}
                  segments={item.text ? parseAgentTags(item.text) : undefined}
                />
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
            }}
          />
        )}
        {pendingFile && (
          <FilePreviewChip fileName={pendingFile.name} onDismiss={() => setPendingFile(null)} />
        )}
        {voiceNotice && (
          <Text style={{ color: colors.fg3, textAlign: 'center', marginBottom: 4 }}>
            {voiceNotice}
          </Text>
        )}
        <AskBar
          ref={askBarRef}
          value={draft.text}
          tag={draft.tag}
          onChangeText={(next) => setDraft(next)}
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
          disabled={isStreaming}
          blockedAgents={blocked}
        />
      </KeyboardAvoidingView>
    </Screen>
  );
}
