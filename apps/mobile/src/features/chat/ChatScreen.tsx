import React, { useState } from 'react';
import { FlatList, KeyboardAvoidingView, Platform, View } from 'react-native';
import { AgentBadge, AskBar, Bubble, Screen, useTheme } from '@life-agents/ui';
import { useRouter } from 'expo-router';
import { useChat } from './useChat';
import { CommandPalette } from './CommandPalette';
import { matchCommands } from './commands';

export function ChatScreen() {
  const { messages, send } = useChat();
  const { spacing } = useTheme();
  const router = useRouter();
  const [input, setInput] = useState('');
  const commandMatches = matchCommands(input);

  return (
    <Screen>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <FlatList
          data={messages}
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
        {commandMatches.length > 0 && (
          <CommandPalette
            items={commandMatches}
            onSelect={(c) => setInput(c.name + ' ')}
          />
        )}
        <AskBar
          value={input}
          onChangeText={setInput}
          onSubmit={(text) => {
            send(text);
            setInput('');
          }}
          onAction={() => router.push('/quick-log')}
          onVoice={() => {}}
        />
      </KeyboardAvoidingView>
    </Screen>
  );
}
