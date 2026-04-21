import React from 'react';
import { FlatList, KeyboardAvoidingView, Platform, View } from 'react-native';
import { useRouter } from 'expo-router';
import { AgentBadge, AskBar, Bubble, Screen, useTheme } from '@life-agents/ui';
import { useChat } from './useChat';

export function ChatScreen() {
  const router = useRouter();
  const { messages, send } = useChat();
  const { spacing } = useTheme();
  return (
    <Screen>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <FlatList
          data={messages}
          inverted={false}
          keyExtractor={(m) => m.id}
          contentContainerStyle={{ padding: spacing.s3, gap: spacing.s2 }}
          renderItem={({ item }) =>
            item.kind === 'user' ? (
              <Bubble variant="user">{item.text}</Bubble>
            ) : (
              <View style={{ gap: spacing.s1, alignItems: 'flex-start' }}>
                {item.agent && <AgentBadge agent={item.agent} />}
                <Bubble variant="assistant">{item.text || '…'}</Bubble>
              </View>
            )
          }
        />
        <AskBar
          onSubmit={send}
          onAction={() => router.push('/quick-log')}
          onVoice={() => {}}
        />
      </KeyboardAvoidingView>
    </Screen>
  );
}
