export type AgentColorId =
  | 'sleep' | 'workout' | 'nutrition' | 'mood' | 'habits'
  | 'medication' | 'recovery' | 'calendar' | 'finance' | 'home' | 'body';

// Pre-computed hex from oklch per-agent hues (dark mode, l=0.82 c=0.12/0.14).
export const AGENT_COLORS: Record<AgentColorId, { solid: string; tint: string }> = {
  sleep:      { solid: '#5b8ef5', tint: '#5b8ef520' }, // hue 255
  workout:    { solid: '#f5804e', tint: '#f5804e20' }, // hue 20
  nutrition:  { solid: '#4ec47a', tint: '#4ec47a20' }, // hue 135
  mood:       { solid: '#e05bd4', tint: '#e05bd420' }, // hue 310
  habits:     { solid: '#8fc43e', tint: '#8fc43e20' }, // hue 85
  medication: { solid: '#3ec4c4', tint: '#3ec4c420' }, // hue 195
  recovery:   { solid: '#3ec487', tint: '#3ec48720' }, // hue 165
  calendar:   { solid: '#4e7af5', tint: '#4e7af520' }, // hue 235
  finance:    { solid: '#c4a53e', tint: '#c4a53e20' }, // hue 45
  home:       { solid: '#4e9af5', tint: '#4e9af520' }, // hue 210
  body:       { solid: '#e05b7a', tint: '#e05b7a20' }, // hue 340
};

export function agentSolid(id: AgentColorId | string): string {
  return (AGENT_COLORS as Record<string, { solid: string }>)[id]?.solid ?? '#c88600';
}

export function agentTint(id: AgentColorId | string): string {
  return (AGENT_COLORS as Record<string, { tint: string }>)[id]?.tint ?? '#c8860020';
}
