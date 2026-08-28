import type { AgentId } from '@life-agents/ui';

const AGENT_NAMES: readonly AgentId[] = [
  'sleep', 'workout', 'nutrition', 'mood', 'habits',
  'recovery', 'medication', 'finance', 'calendar', 'home', 'body',
];

const TAG_RE = new RegExp(`(^|\\s)/(${AGENT_NAMES.join('|')})(?=\\s|$)`, 'g');

export type Segment = string | { tag: AgentId };

export function parseAgentTags(text: string): Segment[] {
  if (!text) return [];
  const segments: Segment[] = [];
  let lastIndex = 0;
  for (const match of text.matchAll(TAG_RE)) {
    const idx = match.index ?? 0;
    const lead = match[1] ?? '';
    const name = match[2] ?? '';
    const tagStart = idx + lead.length;
    if (tagStart > lastIndex) {
      segments.push(text.slice(lastIndex, tagStart));
    }
    segments.push({ tag: name as AgentId });
    lastIndex = tagStart + 1 + name.length; // 1 = the slash
  }
  if (lastIndex < text.length) {
    segments.push(text.slice(lastIndex));
  }
  return segments.length > 0 ? segments : [text];
}
