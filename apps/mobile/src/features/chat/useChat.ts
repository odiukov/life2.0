import { useCallback, useRef, useState } from 'react';
import { apiMode } from '@/api/client';
import { mockAssistantStream, StreamEvent } from './mockStream';
import { realAssistantStream } from './realStream';
import { realFileStream } from './realFileStream';
import type { AgentId } from '@life-agents/ui';

const AGENT_NAMES = [
  'sleep',
  'workout',
  'nutrition',
  'mood',
  'habits',
  'recovery',
  'medication',
  'finance',
  'calendar',
  'home',
  'body',
] as const satisfies readonly AgentId[];

const LEADING_TAG_RE = new RegExp(`^/(${AGENT_NAMES.join('|')})\\s(.*)$`, 's');

function promoteLeadingTag(text: string): { tag?: AgentId; text: string } {
  const match = LEADING_TAG_RE.exec(text);
  if (!match) return { text };
  return { tag: match[1] as AgentId, text: match[2] ?? '' };
}

type Message =
  | { kind: 'user'; id: string; tag?: AgentId; text: string }
  | {
      kind: 'assistant';
      id: string;
      agent?: AgentId;
      consulted?: AgentId[];
      text: string;
      streaming: boolean;
    };

const assistantStream = apiMode === 'mock' ? mockAssistantStream : realAssistantStream;
const ORCHESTRATOR_ONLY_TAGS = new Set<AgentId>(['calendar', 'home', 'body']);

const newThreadId = () => 'mobile-' + Date.now();

export type SendInput = { tag?: AgentId; text: string };

export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const threadIdRef = useRef(newThreadId());

  const resetThread = useCallback(() => {
    threadIdRef.current = newThreadId();
    setMessages([
      {
        kind: 'assistant',
        id: `a${Date.now()}`,
        text: 'New conversation started ✨',
        streaming: false,
      },
    ]);
  }, []);

  const _consumeStream = useCallback(async (stream: AsyncGenerator<StreamEvent>, aid: string) => {
    let buffer = '';
    let agent: AgentId | undefined;
    let consulted: AgentId[] | undefined;
    for await (const ev of stream) {
      if (ev.type === 'token') {
        buffer += ev.content;
        setMessages((m) =>
          m.map((msg) =>
            msg.id === aid && msg.kind === 'assistant'
              ? { ...msg, text: buffer, agent, consulted }
              : msg,
          ),
        );
      } else if (ev.type === 'agent_routed') {
        agent = ev.primary;
        setMessages((m) =>
          m.map((msg) => (msg.id === aid && msg.kind === 'assistant' ? { ...msg, agent } : msg)),
        );
      } else if (ev.type === 'agent_consulted') {
        consulted = ev.peers;
        setMessages((m) =>
          m.map((msg) =>
            msg.id === aid && msg.kind === 'assistant' ? { ...msg, consulted } : msg,
          ),
        );
      } else if (ev.type === 'done') {
        setMessages((m) =>
          m.map((msg) =>
            msg.id === aid && msg.kind === 'assistant' ? { ...msg, streaming: false } : msg,
          ),
        );
      }
    }
  }, []);

  const send = useCallback(
    async (input: SendInput | string) => {
      const { tag, text } = typeof input === 'string' ? promoteLeadingTag(input) : input;
      const trimmed = text.trim();
      if (!tag && trimmed === '/new') {
        resetThread();
        return;
      }
      const uid = `u${Date.now()}`;
      setMessages((m) => [...m, { kind: 'user', id: uid, tag, text }]);
      const aid = `a${Date.now()}`;
      setMessages((m) => [...m, { kind: 'assistant', id: aid, text: '', streaming: true }]);
      const useOrchestrator = tag != null && ORCHESTRATOR_ONLY_TAGS.has(tag);
      const streamText = useOrchestrator ? `/${tag} ${trimmed}`.trim() : text;
      await _consumeStream(
        assistantStream(
          streamText,
          threadIdRef.current,
          tag && !useOrchestrator ? { agent: tag } : undefined,
        ) as AsyncGenerator<StreamEvent>,
        aid,
      );
    },
    [resetThread, _consumeStream],
  );

  const sendFile = useCallback(
    async (fileUri: string, fileName: string, agentHint?: string) => {
      const uid = `u${Date.now()}`;
      setMessages((m) => [...m, { kind: 'user', id: uid, text: `📎 ${fileName}` }]);
      const aid = `a${Date.now()}`;
      setMessages((m) => [...m, { kind: 'assistant', id: aid, text: '', streaming: true }]);
      await _consumeStream(realFileStream(fileUri, fileName, threadIdRef.current, agentHint), aid);
    },
    [_consumeStream],
  );

  return { messages, send, sendFile, resetThread };
}
