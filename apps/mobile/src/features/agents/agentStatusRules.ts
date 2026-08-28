// apps/mobile/src/features/agents/agentStatusRules.ts
import type { AgentId } from '@life-agents/ui';
import type { IntegrationId } from '@/features/integrations/store';
import type { HomeSummary } from '@/features/home/useHomeSummary';
import type { MeProfile } from '@/features/profile/useMeProfile';
import { HINT_COPY } from './agentCopy';

export type AgentStatus = 'ready' | 'needs_setup' | 'no_data';

export type CtaTarget =
  | { kind: 'integrations'; panel?: 'ha' | 'yazio' | 'calendar' | 'apple-health' | 'garmin' }
  | { kind: 'chat-prefill'; text: string; tag?: AgentId }
  | { kind: 'finance-upload' };

export type AgentRow = {
  id: AgentId;
  description: string;
  status: AgentStatus;
  hint: string | null;
  cta: CtaTarget | null;
};

export type RuleSources = {
  integrations: Set<IntegrationId>;
  summary: HomeSummary | undefined;
  peerOnline: Map<string, boolean>;
  meProfile: MeProfile | null | undefined;
};

function hasBodyProfile(p: MeProfile | null | undefined): boolean {
  if (!p) return false;
  return p.height_cm != null || p.weight_kg != null;
}

export const AGENT_DISPLAY_ORDER: readonly AgentId[] = [
  'sleep',
  'workout',
  'nutrition',
  'recovery',
  'body',
  'mood',
  'habits',
  'medication',
  'calendar',
  'home',
  'finance',
];

const VALID_AGENT_IDS: ReadonlySet<AgentId> = new Set<AgentId>(AGENT_DISPLAY_ORDER);

export function isAgentId(value: string | undefined): value is AgentId {
  return !!value && VALID_AGENT_IDS.has(value as AgentId);
}

const ready = (): { status: AgentStatus; hint: string | null; cta: CtaTarget | null } => ({
  status: 'ready',
  hint: null,
  cta: null,
});

function hasAgentMetric(summary: HomeSummary | undefined, id: AgentId): boolean {
  if (!summary) return false;
  const a = summary.agents.find((x) => x.agent === id);
  return Boolean(a && a.metric && a.metric.trim().length > 0);
}

export function computeAgentStatus(
  id: AgentId,
  s: RuleSources,
): { status: AgentStatus; hint: string | null; cta: CtaTarget | null } {
  switch (id) {
    case 'home':
      return s.integrations.has('ha')
        ? ready()
        : {
            status: 'needs_setup',
            hint: HINT_COPY.home_no_token,
            cta: { kind: 'integrations', panel: 'ha' },
          };

    case 'calendar':
      return s.integrations.has('calendar')
        ? ready()
        : {
            status: 'needs_setup',
            hint: HINT_COPY.calendar_not_connected,
            cta: { kind: 'integrations', panel: 'calendar' },
          };

    case 'sleep': {
      const hasSource = s.integrations.has('apple-health') || s.integrations.has('garmin');
      if (!hasSource) {
        return {
          status: 'needs_setup',
          hint: HINT_COPY.sleep_no_source,
          cta: { kind: 'integrations', panel: 'apple-health' },
        };
      }
      return hasAgentMetric(s.summary, 'sleep')
        ? ready()
        : { status: 'no_data', hint: HINT_COPY.no_recent_data, cta: null };
    }

    case 'workout': {
      const hasSource =
        s.integrations.has('apple-health') ||
        s.integrations.has('garmin') ||
        s.integrations.has('strava');
      if (!hasSource) {
        return {
          status: 'needs_setup',
          hint: HINT_COPY.workout_no_source,
          cta: { kind: 'integrations', panel: 'apple-health' },
        };
      }
      return hasAgentMetric(s.summary, 'workout')
        ? ready()
        : { status: 'no_data', hint: HINT_COPY.no_recent_data, cta: null };
    }

    case 'recovery': {
      const hasSource = s.integrations.has('garmin') || s.integrations.has('apple-health');
      if (!hasSource) {
        return {
          status: 'needs_setup',
          hint: HINT_COPY.recovery_no_source,
          cta: { kind: 'integrations', panel: 'garmin' },
        };
      }
      return hasAgentMetric(s.summary, 'recovery')
        ? ready()
        : { status: 'no_data', hint: HINT_COPY.no_recent_data, cta: null };
    }

    case 'nutrition': {
      const hasYazio = s.integrations.has('yazio');
      const hasMetric = hasAgentMetric(s.summary, 'nutrition');
      if (hasMetric) return ready(); // yazio OR manual logging both surface here
      if (hasYazio) {
        return { status: 'no_data', hint: HINT_COPY.no_recent_data, cta: null };
      }
      return {
        status: 'needs_setup',
        hint: HINT_COPY.nutrition_no_source,
        cta: { kind: 'integrations', panel: 'yazio' },
      };
    }

    case 'body':
      return hasAgentMetric(s.summary, 'body') || hasBodyProfile(s.meProfile)
        ? ready()
        : {
            status: 'needs_setup',
            hint: HINT_COPY.body_no_data,
            cta: { kind: 'chat-prefill', text: '', tag: 'body' },
          };

    case 'mood':
      return hasAgentMetric(s.summary, 'mood')
        ? ready()
        : {
            status: 'needs_setup',
            hint: HINT_COPY.mood_no_data,
            cta: { kind: 'chat-prefill', text: '', tag: 'mood' },
          };

    case 'habits':
      return hasAgentMetric(s.summary, 'habits')
        ? ready()
        : {
            status: 'needs_setup',
            hint: HINT_COPY.habits_no_data,
            cta: { kind: 'chat-prefill', text: '', tag: 'habits' },
          };

    case 'medication':
      return hasAgentMetric(s.summary, 'medication')
        ? ready()
        : {
            status: 'needs_setup',
            hint: HINT_COPY.medication_no_data,
            cta: { kind: 'chat-prefill', text: '', tag: 'medication' },
          };

    case 'finance': {
      const hasMetric = hasAgentMetric(s.summary, 'finance');
      if (hasMetric) return ready();
      if (s.integrations.has('payoneer')) {
        return { status: 'no_data', hint: HINT_COPY.no_recent_data, cta: null };
      }
      return {
        status: 'needs_setup',
        hint: HINT_COPY.finance_no_data,
        cta: { kind: 'finance-upload' },
      };
    }
  }
}
