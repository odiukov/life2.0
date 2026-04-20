import React from 'react';
import { AgentBadge } from './index';
import type { AgentId } from './index';

export default { title: 'chat/AgentBadge', component: AgentBadge };

const agents: AgentId[] = [
  'sleep', 'workout', 'nutrition', 'mood', 'habits',
  'recovery', 'medication', 'finance', 'calendar', 'home',
];

export const { Sleep, Workout, Nutrition, Mood, Habits, Recovery, Medication, Finance, Calendar, Home } =
  Object.fromEntries(
    agents.map((agent) => [
      agent.charAt(0).toUpperCase() + agent.slice(1),
      () => <AgentBadge agent={agent} />,
    ]),
  ) as Record<string, React.FC>;
