import { useCallback, useRef, useState } from 'react';
import { apiMode } from '@/api/client';
import { mockAssistantStream, StreamEvent } from './mockStream';
import { realAssistantStream, THREAD_ID } from './realStream';

type AgentType = Extract<StreamEvent, { type: 'agent' }>['agent'];

type Message =
  | { kind: 'user'; id: string; text: string }
  | { kind: 'assistant'; id: string; agent?: AgentType; text: string; streaming: boolean };

const assistantStream = apiMode === 'mock' ? mockAssistantStream : realAssistantStream;

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const streamingIdRef = useRef(0);

  const send = useCallback(async (text: string) => {
    const uid = `u${Date.now()}`;
    setMessages((m) => [...m, { kind: 'user', id: uid, text }]);
    const aid = `a${Date.now()}`;
    streamingIdRef.current += 1;
    setMessages((m) => [...m, { kind: 'assistant', id: aid, text: '', streaming: true }]);
    let buffer = '';
    let agent: AgentType | undefined;
    for await (const ev of assistantStream(text, THREAD_ID)) {
      if (ev.type === 'token') {
        buffer += ev.content;
        setMessages((m) =>
          m.map((msg) => (msg.id === aid && msg.kind === 'assistant' ? { ...msg, text: buffer, agent } : msg)),
        );
      } else if (ev.type === 'agent') {
        agent = ev.agent;
        setMessages((m) => m.map((msg) => (msg.id === aid && msg.kind === 'assistant' ? { ...msg, agent } : msg)));
      } else if (ev.type === 'done') {
        setMessages((m) => m.map((msg) => (msg.id === aid && msg.kind === 'assistant' ? { ...msg, streaming: false } : msg)));
      }
    }
  }, []);

  return { messages, send };
}
