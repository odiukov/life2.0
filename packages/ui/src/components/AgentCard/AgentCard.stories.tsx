import React from 'react';
import { AgentCard } from './index';

export default { title: 'dashboard/AgentCard', component: AgentCard };

export const Success = () => (
  <AgentCard agent="sleep" label="Sleep" metric="7h 42m" tint="success" />
);

export const Warn = () => (
  <AgentCard agent="nutrition" label="Nutrition" metric="1 800 kcal" tint="warn" />
);

export const Danger = () => (
  <AgentCard agent="workout" label="Workout" metric="0 sessions" tint="danger" />
);

export const Neutral = () => (
  <AgentCard agent="mood" label="Mood" metric="—" tint="neutral" />
);
