import React from 'react';
import { AgentMark } from './index';
import type { AgentId } from '../AgentBadge';

export default { title: 'agents/AgentMark', component: AgentMark };

const agents: AgentId[] = [
  'sleep', 'workout', 'nutrition', 'mood', 'habits',
  'recovery', 'medication', 'finance', 'calendar', 'home',
];

export const { Sleep, Workout, Nutrition, Mood, Habits, Recovery, Medication, Finance, Calendar, Home } =
  Object.fromEntries(
    agents.map((agent) => [
      agent.charAt(0).toUpperCase() + agent.slice(1),
      () => <AgentMark agent={agent} size={24} />,
    ]),
  ) as Record<string, React.FC>;
