// apps/mobile/src/features/agents/agentStatusRules.test.ts
import {
  computeAgentStatus,
  AGENT_DISPLAY_ORDER,
  isAgentId,
  type RuleSources,
} from './agentStatusRules';

function makeSources(overrides: Partial<RuleSources> = {}): RuleSources {
  return {
    integrations: new Set(),
    summary: undefined,
    peerOnline: new Map(),
    meProfile: null,
    ...overrides,
  };
}

describe('AGENT_DISPLAY_ORDER', () => {
  it('lists 11 unique agents', () => {
    expect(AGENT_DISPLAY_ORDER).toHaveLength(11);
    expect(new Set(AGENT_DISPLAY_ORDER).size).toBe(11);
  });
});

describe('isAgentId', () => {
  it('returns true for a valid agent id', () => {
    expect(isAgentId('sleep')).toBe(true);
    expect(isAgentId('finance')).toBe(true);
  });

  it('returns false for an invalid or empty value', () => {
    expect(isAgentId('not-an-agent')).toBe(false);
    expect(isAgentId(undefined)).toBe(false);
    expect(isAgentId('')).toBe(false);
  });
});

describe('computeAgentStatus', () => {
  // ── home (integration only) ────────────────────────────────────────────
  it('home is needs_setup when ha integration not connected', () => {
    const r = computeAgentStatus('home', makeSources());
    expect(r.status).toBe('needs_setup');
    expect(r.hint).toBe('Add Home Assistant token in Settings');
    expect(r.cta).toEqual({ kind: 'integrations', panel: 'ha' });
  });

  it('home is ready when ha is connected', () => {
    const r = computeAgentStatus(
      'home',
      makeSources({
        integrations: new Set(['ha']),
      }),
    );
    expect(r.status).toBe('ready');
    expect(r.hint).toBeNull();
    expect(r.cta).toBeNull();
  });

  // ── calendar (integration only) ────────────────────────────────────────
  it('calendar is needs_setup when not connected', () => {
    const r = computeAgentStatus('calendar', makeSources());
    expect(r.status).toBe('needs_setup');
    expect(r.cta).toEqual({ kind: 'integrations', panel: 'calendar' });
  });

  it('calendar is ready when connected', () => {
    const r = computeAgentStatus(
      'calendar',
      makeSources({
        integrations: new Set(['calendar']),
      }),
    );
    expect(r.status).toBe('ready');
  });

  // ── sleep (integration + data) ─────────────────────────────────────────
  it('sleep is needs_setup when no fitness source connected', () => {
    const r = computeAgentStatus('sleep', makeSources());
    expect(r.status).toBe('needs_setup');
    expect(r.hint).toBe('Connect Apple Health or Garmin to track sleep');
  });

  it('sleep is no_data when source connected but no recent sleep', () => {
    const r = computeAgentStatus(
      'sleep',
      makeSources({
        integrations: new Set(['apple-health']),
        summary: { agents: [] } as any,
      }),
    );
    expect(r.status).toBe('no_data');
    expect(r.hint).toBe('No recent data — pull to refresh on Home');
  });

  it('sleep is ready when source connected and summary has sleep data', () => {
    const r = computeAgentStatus(
      'sleep',
      makeSources({
        integrations: new Set(['apple-health']),
        summary: {
          agents: [
            {
              agent: 'sleep',
              label: 'Sleep',
              metric: '7h 30m',
              detail: null,
              tint: 'success',
              progress: 80,
            },
          ],
        } as any,
      }),
    );
    expect(r.status).toBe('ready');
  });

  // ── workout (integration + data) ───────────────────────────────────────
  it('workout is ready when garmin connected and metric present', () => {
    const r = computeAgentStatus(
      'workout',
      makeSources({
        integrations: new Set(['garmin']),
        summary: {
          agents: [
            {
              agent: 'workout',
              label: 'Training',
              metric: '5k run',
              detail: null,
              tint: 'success',
              progress: null,
            },
          ],
        } as any,
      }),
    );
    expect(r.status).toBe('ready');
  });

  // ── mood (data only, no integration required) ──────────────────────────
  it('mood is needs_setup when no logs ever', () => {
    const r = computeAgentStatus(
      'mood',
      makeSources({
        summary: { agents: [] } as any,
      }),
    );
    expect(r.status).toBe('needs_setup');
    expect(r.hint).toBe('Log your first mood — how do you feel?');
    expect(r.cta).toEqual({ kind: 'chat-prefill', text: '', tag: 'mood' });
  });

  it('mood is ready when at least one mood log exists', () => {
    const r = computeAgentStatus(
      'mood',
      makeSources({
        summary: {
          agents: [
            {
              agent: 'mood',
              label: 'Mood',
              metric: '7/10',
              detail: null,
              tint: 'success',
              progress: null,
            },
          ],
        } as any,
      }),
    );
    expect(r.status).toBe('ready');
  });

  // ── body (profile-driven, no integration required) ────────────────────
  it('body is needs_setup when no profile and no metric', () => {
    const r = computeAgentStatus('body', makeSources());
    expect(r.status).toBe('needs_setup');
    expect(r.hint).toBe('Tell me your weight and height in chat');
    expect(r.cta).toEqual({ kind: 'chat-prefill', text: '', tag: 'body' });
  });

  it('body is ready when /me/profile has weight_kg', () => {
    const r = computeAgentStatus(
      'body',
      makeSources({
        meProfile: {
          height_cm: null,
          weight_kg: 78,
          age: null,
          sex: null,
          activity_level: null,
          calorie_goal_override: null,
        },
      }),
    );
    expect(r.status).toBe('ready');
  });

  it('body is ready when /me/profile has height_cm only', () => {
    const r = computeAgentStatus(
      'body',
      makeSources({
        meProfile: {
          height_cm: 182,
          weight_kg: null,
          age: null,
          sex: null,
          activity_level: null,
          calorie_goal_override: null,
        },
      }),
    );
    expect(r.status).toBe('ready');
  });

  // ── nutrition (multi-source) ───────────────────────────────────────────
  it('nutrition is ready when yazio connected and metric present', () => {
    const r = computeAgentStatus(
      'nutrition',
      makeSources({
        integrations: new Set(['yazio']),
        summary: {
          agents: [
            {
              agent: 'nutrition',
              label: 'Nutrition',
              metric: '1800 kcal',
              detail: null,
              tint: 'success',
              progress: null,
            },
          ],
        } as any,
      }),
    );
    expect(r.status).toBe('ready');
  });

  it('nutrition is ready when no integration but a meal was logged manually', () => {
    const r = computeAgentStatus(
      'nutrition',
      makeSources({
        summary: {
          agents: [
            {
              agent: 'nutrition',
              label: 'Nutrition',
              metric: '1800 kcal',
              detail: null,
              tint: 'success',
              progress: null,
            },
          ],
        } as any,
      }),
    );
    expect(r.status).toBe('ready');
  });

  it('nutrition is needs_setup when no integration and no logs', () => {
    const r = computeAgentStatus('nutrition', makeSources());
    expect(r.status).toBe('needs_setup');
    expect(r.cta).toEqual({ kind: 'integrations', panel: 'yazio' });
  });

  // ── finance ────────────────────────────────────────────────────────────
  it('finance is ready when finance metric is present', () => {
    const r = computeAgentStatus(
      'finance',
      makeSources({
        summary: {
          agents: [
            {
              agent: 'finance',
              label: 'Finance',
              metric: '€1,200',
              detail: null,
              tint: 'success',
              progress: null,
            },
          ],
        } as any,
      }),
    );
    expect(r.status).toBe('ready');
  });

  it('finance is no_data when payoneer connected but no metric', () => {
    const r = computeAgentStatus(
      'finance',
      makeSources({
        integrations: new Set(['payoneer']),
        summary: { agents: [] } as any,
      }),
    );
    expect(r.status).toBe('no_data');
    expect(r.hint).toBe('No recent data — pull to refresh on Home');
    expect(r.cta).toBeNull();
  });

  it('finance is needs_setup with no integration and no uploads', () => {
    const r = computeAgentStatus('finance', makeSources());
    expect(r.status).toBe('needs_setup');
    expect(r.cta).toEqual({ kind: 'finance-upload' });
  });
});
