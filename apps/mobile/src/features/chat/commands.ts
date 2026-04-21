import type { AgentId } from '@life-agents/ui';

export type ChatCommand = {
  name: string;
  agent: AgentId;
  hint: string;
};

export const COMMANDS: readonly ChatCommand[] = [
  { name: '/sleep',      agent: 'sleep',      hint: 'Log sleep or ask about sleep' },
  { name: '/workout',    agent: 'workout',    hint: "Log a workout or ask about training" },
  { name: '/nutrition',  agent: 'nutrition',  hint: "Log a meal or check today's intake" },
  { name: '/mood',       agent: 'mood',       hint: 'Log mood / energy / stress' },
  { name: '/journal',    agent: 'mood',       hint: 'Free-form journal entry' },
  { name: '/habit',      agent: 'habits',     hint: 'Log a habit check-in' },
  { name: '/habits',     agent: 'habits',     hint: 'List active habits' },
  { name: '/med',        agent: 'medication', hint: 'Log medication taken' },
  { name: '/recovery',   agent: 'recovery',   hint: "Get today's recovery readiness" },
  { name: '/dashboard',  agent: 'calendar',   hint: 'Full dashboard dump' },
  { name: '/new',        agent: 'home',       hint: 'Start a new chat thread' },
] as const;

export function matchCommands(input: string): readonly ChatCommand[] {
  if (!input.startsWith('/')) return [];
  const q = input.toLowerCase();
  const word = q.split(/\s/)[0] ?? q; // only match the first token
  return COMMANDS.filter((c) => c.name.startsWith(word));
}
