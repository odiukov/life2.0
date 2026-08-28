import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import {
  AgentMark,
  BigRing,
  Card,
  Icon,
  InsightTip,
  Pill,
  SectionLabel,
  Sparkbars,
  StatRow,
  agentSolid,
  useTheme,
} from '@life-agents/ui';
import type { AgentId } from '@life-agents/ui';
import { AGENT_COPY } from '@/features/agents/agentCopy';
import { useConnectedIntegrations } from '@/features/integrations/store';
import { AGENT_META } from '../dash/agentMeta';
import { useHomeSummary } from './useHomeSummary';
import { useAgentDetail, type AgentDetail } from './useAgentDetail';

/**
 * Content body of the agent detail view — hero header, per-agent body, and
 * quick actions. No outer scroll wrapper, no back button, no container
 * padding. Designed to be embedded inside a bottom sheet (AgentDetailSheet)
 * or a fullscreen scroll wrapper (AgentDetailScreen).
 */
export function AgentDetailContent({
  agentId,
  enabled = true,
  onAction,
}: {
  agentId: AgentId;
  /** Whether to fetch backend detail. Pass false while sheet is closed. */
  enabled?: boolean;
  /** Called when the user taps a quick action. Receives the raw command message. */
  onAction: (message: string) => void;
}) {
  const { colors, typography } = useTheme();
  const tint = agentSolid(agentId);
  const copy = AGENT_COPY[agentId];
  const meta = AGENT_META[agentId];

  const { data: summary } = useHomeSummary();
  const { data: detail } = useAgentDetail(agentId, enabled);
  const connected = useConnectedIntegrations() as unknown as Set<string>;

  const isReady = !needsSetup(agentId, connected);

  return (
    <View>
      {/* Hero */}
      <View style={styles.hero}>
        <View
          style={[
            styles.heroAvatar,
            {
              backgroundColor: tint + '24',
              borderColor: tint + '44',
            },
          ]}
        >
          <AgentMark agent={agentId} size={56} withBackground={false} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text
            style={{
              fontFamily: typography.title1.fontFamily,
              fontSize: 22,
              color: colors.fg1,
              fontWeight: '600',
              letterSpacing: -0.5,
            }}
          >
            {copy.label}
          </Text>
          <Text style={{ fontSize: 12.5, color: colors.fg3, marginTop: 2 }}>
            {copy.description}
          </Text>
          <View style={styles.statusRow}>
            <View
              style={{
                width: 7,
                height: 7,
                borderRadius: 4,
                backgroundColor: isReady ? colors.success : colors.warn,
              }}
            />
            <Text style={{ fontSize: 11.5, color: colors.fg2 }}>
              {isReady ? 'Ready' : 'Needs setup'}
            </Text>
          </View>
        </View>
      </View>

      {/* Per-agent body */}
      <AgentBody
        agentId={agentId}
        tint={tint}
        summary={summary}
        detail={detail}
        insight={detail?.insight ?? null}
        connected={connected}
      />

      {/* Quick actions */}
      {meta.actions.length > 0 && (
        <View style={{ marginTop: 14 }}>
          <SectionLabel>Quick actions</SectionLabel>
          <View style={{ gap: 8 }}>
            {meta.actions.map((act) => (
              <Card key={act.label} pad={14} onPress={() => onAction(act.message)}>
                <View style={styles.actionRow}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={{ fontSize: 13.5, color: colors.fg1, fontWeight: '600' }}>
                      {act.label}
                    </Text>
                    <Text style={{ fontSize: 11.5, color: colors.fg3, marginTop: 2 }}>
                      {act.subtitle}
                    </Text>
                  </View>
                  <View
                    style={{
                      backgroundColor: tint + '22',
                      paddingHorizontal: 8,
                      paddingVertical: 4,
                      borderRadius: 8,
                    }}
                  >
                    <Text
                      style={{
                        fontFamily: typography.mono.fontFamily,
                        fontSize: 11,
                        color: tint,
                      }}
                    >
                      /{agentId}
                    </Text>
                  </View>
                  <Icon name="CaretRight" size={16} color={colors.fg4} />
                </View>
              </Card>
            ))}
          </View>
        </View>
      )}
    </View>
  );
}

/**
 * Fullscreen route wrapper around AgentDetailContent — kept for the
 * /(tabs)/dash/[agent] deep-link route. The primary in-app entry point is
 * AgentDetailSheet.
 */
export function AgentDetailScreen({ agentId }: { agentId: AgentId }) {
  const { colors } = useTheme();
  const router = useRouter();

  function handleAction(message: string) {
    const tagged = `/${agentId} ${message}`;
    router.push({ pathname: '/(tabs)/chat', params: { send: tagged } } as never);
  }

  return (
    <ScrollView
      style={{ flex: 1, backgroundColor: colors.bg1 }}
      contentContainerStyle={styles.container}
      showsVerticalScrollIndicator={false}
    >
      <Pressable onPress={() => router.back()} style={styles.backBtn} hitSlop={12}>
        <Icon name="CaretLeft" size={18} color={colors.fg2} />
        <Text style={{ color: colors.fg2, fontSize: 14 }}>Home</Text>
      </Pressable>
      <AgentDetailContent agentId={agentId} onAction={handleAction} />
    </ScrollView>
  );
}

function needsSetup(id: AgentId, connected: Set<string>): boolean {
  if (id === 'calendar') return !connected.has('calendar');
  if (id === 'finance') return !connected.has('payoneer');
  if (id === 'home') return !connected.has('ha');
  return false;
}

type SummaryData = ReturnType<typeof useHomeSummary>['data'];

function AgentBody({
  agentId,
  tint,
  summary,
  detail,
  insight,
  connected,
}: {
  agentId: AgentId;
  tint: string;
  summary: SummaryData;
  detail?: AgentDetail;
  insight: string | null;
  connected: Set<string>;
}) {
  switch (agentId) {
    case 'sleep':
      return <SleepBody tint={tint} summary={summary} insight={insight} />;
    case 'workout':
      return <WorkoutBody tint={tint} summary={summary} insight={insight} />;
    case 'nutrition':
      return <NutritionBody tint={tint} summary={summary} detail={detail} insight={insight} />;
    case 'recovery':
      return <RecoveryBody tint={tint} summary={summary} insight={insight} />;
    case 'habits':
      return <HabitsBody tint={tint} />;
    case 'medication':
      return <MedicationBody tint={tint} insight={insight} />;
    case 'mood':
      return <MoodBody tint={tint} />;
    case 'body':
      return <BodyBody tint={tint} summary={summary} insight={insight} />;
    case 'calendar':
      return <CalendarBody tint={tint} connected={connected} detail={detail} insight={insight} />;
    case 'finance':
      return <FinanceBody tint={tint} connected={connected} />;
    case 'home':
      return <HomeBody tint={tint} connected={connected} />;
    default:
      return null;
  }
}

// ─── Per-agent body components ──────────────────────────────────────────────

function SleepBody({
  tint,
  summary,
  insight,
}: {
  tint: string;
  summary: SummaryData;
  insight: string | null;
}) {
  const sleep = summary?.featuredSleep;
  return (
    <Card>
      <SectionLabel right={`Last night · ${sleep?.source ?? 'HealthKit'}`}>
        At a glance
      </SectionLabel>
      <View style={rowGap16}>
        <StatRow
          label="Duration"
          value={sleep?.durationLabel ?? '6h 45m'}
          hint="Goal 8h"
          bar={{ pct: sleep?.durationPct ?? 84 }}
          tint={tint}
        />
        <StatRow
          label="Deep"
          value={sleep?.deepLabel ?? '1h 12m'}
          hint={sleep ? `${sleep.deepPct}% of total` : '18% of total'}
          bar={{ pct: sleep?.deepPct ?? 72 }}
          tint={tint}
        />
        <StatRow
          label="HRV"
          value={sleep && sleep.hrv > 0 ? String(sleep.hrv) : '58'}
          unit="ms"
          hint={sleep?.hrvDelta ?? '+4 vs avg'}
        />
      </View>
      <View style={{ height: 14 }} />
      <SectionLabel>7-day duration</SectionLabel>
      <Sparkbars values={[7.2, 6.4, 7.8, 5.9, 7.1, 6.2, 6.75]} color={tint} height={42} />
      <InsightTip tint={tint}>
        {insight ?? 'Woke twice around 03:10. Try lowering bedroom temp by 1°C tonight.'}
      </InsightTip>
    </Card>
  );
}

function WorkoutBody({
  tint,
  summary,
  insight,
}: {
  tint: string;
  summary: SummaryData;
  insight: string | null;
}) {
  const { colors, typography } = useTheme();
  const w = summary?.featuredWorkout;
  const history = w?.loadHistory ?? [3, 5, 4, 6, 2, 0, 8];
  return (
    <Card>
      <SectionLabel
        right={
          <Pill tone="success" size="sm">
            {w?.workoutDate === 'today' ? 'Today' : 'Yesterday'}
          </Pill>
        }
      >
        Last session
      </SectionLabel>
      <View>
        <Text
          style={{
            fontFamily: typography.title1.fontFamily,
            fontSize: 22,
            color: colors.fg1,
            fontWeight: '600',
            letterSpacing: -0.5,
          }}
        >
          {w?.sessionName ?? 'Zone 2 run'}
        </Text>
        <Text style={{ fontSize: 12.5, color: colors.fg2, marginTop: 4, lineHeight: 18 }}>
          <Text style={{ fontFamily: typography.mono.fontFamily }}>{w?.distanceKm ?? 8.4}</Text> km
          · <Text style={{ fontFamily: typography.mono.fontFamily }}>{w?.kcal ?? 612}</Text> kcal ·{' '}
          <Text style={{ fontFamily: typography.mono.fontFamily }}>{w?.avgHr ?? 148}</Text> bpm avg
        </Text>
      </View>
      <View style={{ height: 16 }} />
      <SectionLabel right="58% of target">7-day load</SectionLabel>
      <Sparkbars values={history} color={tint} height={42} />
      <InsightTip tint={tint}>
        {insight ?? 'Calves are due for a light day tomorrow. Mobility 15 min would help.'}
      </InsightTip>
    </Card>
  );
}

function NutritionBody({
  tint,
  summary,
  detail,
  insight,
}: {
  tint: string;
  summary: SummaryData;
  detail?: AgentDetail;
  insight: string | null;
}) {
  const { colors, typography } = useTheme();
  const n = summary?.featuredNutrition;
  const proteinPct =
    n && n.proteinGoalG > 0 ? Math.min(100, Math.round((n.proteinG / n.proteinGoalG) * 100)) : 66;
  const carbsPct =
    n && n.carbsGoalG > 0 ? Math.min(100, Math.round((n.carbsG / n.carbsGoalG) * 100)) : 76;
  const fatPct = n && n.fatGoalG > 0 ? Math.min(100, Math.round((n.fatG / n.fatGoalG) * 100)) : 68;
  const meals = detail?.meals ?? [];
  return (
    <Card>
      <SectionLabel
        right={
          <Text
            style={{ fontFamily: typography.mono.fontFamily, fontSize: 11.5, color: colors.fg3 }}
          >
            {(n?.kcalConsumed ?? 1420).toLocaleString()}
            <Text style={{ color: colors.fg4 }}>
              {' '}
              / {(n?.kcalGoal ?? 2150).toLocaleString()}
            </Text>{' '}
            kcal
          </Text>
        }
      >
        Today · Yazio
      </SectionLabel>
      <View style={rowGap16}>
        <StatRow
          label="Protein"
          value={String(n?.proteinG ?? 92)}
          unit="g"
          hint={`Goal ${n?.proteinGoalG ?? 140}g`}
          bar={{ pct: proteinPct }}
          tint={tint}
        />
        <StatRow
          label="Carbs"
          value={String(n?.carbsG ?? 168)}
          unit="g"
          hint={`Goal ${n?.carbsGoalG ?? 220}g`}
          bar={{ pct: carbsPct }}
          tint={tint}
        />
        <StatRow
          label="Fat"
          value={String(n?.fatG ?? 48)}
          unit="g"
          hint={`Goal ${n?.fatGoalG ?? 70}g`}
          bar={{ pct: fatPct }}
          tint={tint}
        />
      </View>
      <View style={{ height: 14 }} />
      <SectionLabel>Today's meals</SectionLabel>
      <View style={{ gap: 8 }}>
        {meals.length === 0 && (
          <View style={[styles.listRow, { backgroundColor: colors.bg3 }]}>
            <Text style={{ flex: 1, fontSize: 12.5, color: colors.fg3 }}>
              No meals logged today
            </Text>
          </View>
        )}
        {meals.map((m) => (
          <View
            key={`${m.meal_type}-${m.recorded_at}`}
            style={[styles.listRow, { backgroundColor: colors.bg3 }]}
          >
            <Text style={{ flex: 1, fontSize: 12.5, color: colors.fg1 }}>
              {m.label}
              {m.items.length > 0 ? ` · ${m.items.join(' + ')}` : ''}
            </Text>
            <Text
              style={{
                fontFamily: typography.mono.fontFamily,
                fontSize: 12,
                color: colors.fg3,
              }}
            >
              {m.kcal} kcal
            </Text>
          </View>
        ))}
      </View>
      <InsightTip tint={tint}>
        {insight ??
          '48g short on protein with 6h left. A 200g Greek yogurt + scoop of whey closes it.'}
      </InsightTip>
    </Card>
  );
}

function RecoveryBody({
  tint,
  summary,
  insight,
}: {
  tint: string;
  summary: SummaryData;
  insight: string | null;
}) {
  const ready = summary?.rings?.readyPct ?? 82;
  return (
    <Card>
      <SectionLabel
        right={
          <Pill tone="success" size="sm">
            GREEN
          </Pill>
        }
      >
        Today
      </SectionLabel>
      <View style={{ alignItems: 'center', paddingVertical: 8 }}>
        <BigRing pct={ready} color={tint} value={`${ready}`} label="Ready" />
      </View>
      <SectionLabel>Drivers</SectionLabel>
      <View style={rowGap16}>
        <StatRow
          label="Sleep"
          value={summary?.featuredSleep?.durationLabel ?? '6:45'}
          hint="84% of goal"
          bar={{ pct: summary?.featuredSleep?.durationPct ?? 84 }}
          tint={tint}
        />
        <StatRow
          label="HRV"
          value={summary?.rings?.hrvMs ? String(summary.rings.hrvMs) : '58'}
          unit="ms"
          hint="+4 vs avg"
          bar={{ pct: summary?.rings?.hrvPct ?? 72 }}
          tint={tint}
        />
        <StatRow label="Strain" value="58%" hint="On target" bar={{ pct: 58 }} tint={tint} />
      </View>
      <InsightTip tint={tint}>
        {insight ?? 'Safe for a hard session today. HRV and sleep both trending up.'}
      </InsightTip>
    </Card>
  );
}

function HabitsBody({ tint }: { tint: string }) {
  const { colors } = useTheme();
  const items = [
    { name: 'Meditation', done: true },
    { name: 'Reading', done: true },
    { name: '8k steps', done: true },
    { name: 'Water 8/8', done: false, sub: '4 / 8 glasses' },
    { name: 'Stretch', done: false, sub: 'Pending' },
  ];
  return (
    <Card>
      <SectionLabel right="3 / 5">Today</SectionLabel>
      <View style={{ gap: 6 }}>
        {items.map((h) => (
          <View key={h.name} style={[styles.listRow, { backgroundColor: colors.bg3 }]}>
            <View
              style={{
                width: 20,
                height: 20,
                borderRadius: 10,
                backgroundColor: h.done ? tint : 'transparent',
                borderWidth: 1.5,
                borderColor: h.done ? tint : colors.border,
                alignItems: 'center',
                justifyContent: 'center',
                marginRight: 10,
              }}
            >
              {h.done && <Icon name="Check" size={12} color={colors.bg1} weight="bold" />}
            </View>
            <Text
              style={{
                flex: 1,
                fontSize: 13,
                color: h.done ? colors.fg2 : colors.fg1,
                textDecorationLine: h.done ? 'line-through' : 'none',
              }}
            >
              {h.name}
            </Text>
            {h.sub && <Text style={{ fontSize: 11, color: colors.fg3 }}>{h.sub}</Text>}
          </View>
        ))}
      </View>
    </Card>
  );
}

function MedicationBody({ tint, insight }: { tint: string; insight: string | null }) {
  const { colors, typography } = useTheme();
  const items = [
    { name: 'Vitamin D', dose: '4000 IU', time: '08:00', state: 'taken' as const },
    { name: 'Omega-3', dose: '1g', time: '08:00', state: 'taken' as const },
    { name: 'Magnesium', dose: '400 mg', time: '20:00', state: 'pending' as const },
  ];
  return (
    <Card>
      <SectionLabel
        right={
          <Pill tone="warn" size="sm">
            1 PENDING
          </Pill>
        }
      >
        Schedule
      </SectionLabel>
      <View style={{ gap: 6 }}>
        {items.map((m) => (
          <View key={m.name} style={[styles.listRow, { backgroundColor: colors.bg3 }]}>
            <View
              style={{
                width: 32,
                height: 32,
                borderRadius: 16,
                backgroundColor: m.state === 'taken' ? colors.successSoft : colors.warnSoft,
                alignItems: 'center',
                justifyContent: 'center',
                marginRight: 12,
              }}
            >
              <Icon
                name="Pill"
                size={15}
                color={m.state === 'taken' ? colors.success : colors.warn}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={{ fontSize: 13, color: colors.fg1, fontWeight: '600' }}>{m.name}</Text>
              <Text style={{ fontSize: 11, color: colors.fg3, marginTop: 1 }}>
                <Text style={{ fontFamily: typography.mono.fontFamily }}>{m.dose}</Text> · {m.time}
              </Text>
            </View>
            {m.state === 'pending' ? (
              <Pill tone="warn" size="sm">
                due 20:00
              </Pill>
            ) : (
              <Icon name="Check" size={16} color={colors.success} weight="bold" />
            )}
          </View>
        ))}
      </View>
      <InsightTip tint={tint}>
        {insight ?? 'Magnesium missed for 2 days. Tap to confirm if you took it already.'}
      </InsightTip>
    </Card>
  );
}

function MoodBody({ tint }: { tint: string }) {
  return (
    <Card>
      <SectionLabel>Last entry</SectionLabel>
      <View style={rowGap16}>
        <StatRow label="Mood" value="7" unit="/ 10" bar={{ pct: 70 }} tint={tint} />
        <StatRow label="Energy" value="6" unit="/ 10" bar={{ pct: 60 }} tint={tint} />
        <StatRow label="Stress" value="4" unit="/ 10" bar={{ pct: 40 }} tint={tint} />
      </View>
      <View style={{ height: 14 }} />
      <SectionLabel>30-day mood</SectionLabel>
      <Sparkbars values={[6, 7, 5, 6, 8, 7, 6, 5, 7, 8, 7, 6, 7]} color={tint} height={42} />
    </Card>
  );
}

function BodyBody({
  tint,
  summary,
  insight,
}: {
  tint: string;
  summary: SummaryData;
  insight: string | null;
}) {
  const { colors } = useTheme();
  const b = summary?.featuredBody;
  return (
    <Card>
      <SectionLabel right="Today · scale">Composition</SectionLabel>
      <View style={rowGap16}>
        <StatRow
          label="Weight"
          value={b?.weightKg ? b.weightKg.toFixed(1) : '78.4'}
          unit="kg"
          hint={
            b?.weightDelta30d != null
              ? `${b.weightDelta30d > 0 ? '+' : ''}${b.weightDelta30d.toFixed(1)} vs 30d`
              : '−0.6 vs 30d'
          }
          bar={{ pct: 60 }}
          tint={tint}
        />
        <StatRow
          label="Body fat"
          value={b?.fatPct ? b.fatPct.toFixed(1) : '26.4'}
          unit="%"
          hint="p90 of 90d"
          bar={{ pct: 90 }}
          tint={colors.warn}
        />
        <StatRow
          label="Muscle"
          value={b?.muscleKg ? b.muscleKg.toFixed(1) : '34.1'}
          unit="kg"
          hint={
            b?.muscleKgDelta30d != null
              ? `${b.muscleKgDelta30d > 0 ? '+' : ''}${b.muscleKgDelta30d.toFixed(1)}`
              : '+0.2'
          }
          bar={{ pct: 55 }}
          tint={tint}
        />
      </View>
      <InsightTip tint={tint}>
        {insight ?? 'Body-fat is in the top 10% of the last 90 days. Worth a look, not a panic.'}
      </InsightTip>
    </Card>
  );
}

type CalendarEventMetric = {
  time?: string;
  name?: string;
  dur?: string;
  all_day?: boolean;
};

function CalendarBody({
  tint,
  connected,
  detail,
  insight,
}: {
  tint: string;
  connected: Set<string>;
  detail?: AgentDetail;
  insight: string | null;
}) {
  const { colors, typography } = useTheme();
  if (!connected.has('calendar')) {
    return (
      <Card>
        <Text
          style={{
            paddingVertical: 20,
            paddingHorizontal: 8,
            textAlign: 'center',
            fontSize: 13,
            color: colors.fg2,
            lineHeight: 19,
          }}
        >
          Connect Google Calendar to see today's meetings and free slots here.
        </Text>
      </Card>
    );
  }
  const rawEvents = detail?.metrics?.events;
  const events: CalendarEventMetric[] = Array.isArray(rawEvents) ? rawEvents : [];
  const busyMinutes =
    typeof detail?.metrics?.busy_minutes === 'number' ? detail.metrics.busy_minutes : 0;
  const busyLabel =
    busyMinutes >= 60
      ? `${Math.floor(busyMinutes / 60)}h${busyMinutes % 60 ? ` ${busyMinutes % 60}m` : ''} busy`
      : `${busyMinutes}m busy`;
  return (
    <Card>
      <SectionLabel right={events.length ? <Pill size="sm">{busyLabel}</Pill> : undefined}>
        Today
      </SectionLabel>
      {events.length > 0 ? (
        <View style={{ gap: 6 }}>
          {events.map((e, i) => (
            <View
              key={`${e.time ?? 'event'}-${i}`}
              style={[styles.listRow, { backgroundColor: colors.bg3 }]}
            >
              <Text
                style={{
                  fontFamily: typography.mono.fontFamily,
                  fontSize: 13,
                  color: tint,
                  fontWeight: '600',
                  width: 58,
                }}
              >
                {e.time ?? '—'}
              </Text>
              <Text style={{ flex: 1, fontSize: 13, color: colors.fg1 }}>
                {e.name ?? 'Untitled'}
              </Text>
              <Text style={{ fontSize: 11, color: colors.fg3 }}>{e.dur ?? ''}</Text>
            </View>
          ))}
        </View>
      ) : (
        <Text style={{ fontSize: 13, color: colors.fg2, lineHeight: 19 }}>
          No events found today.
        </Text>
      )}
      {insight ? <InsightTip tint={tint}>{insight}</InsightTip> : null}
    </Card>
  );
}

function FinanceBody({ tint, connected }: { tint: string; connected: Set<string> }) {
  const { colors, typography } = useTheme();
  if (!connected.has('payoneer')) {
    return (
      <Card>
        <Text
          style={{
            paddingVertical: 20,
            paddingHorizontal: 8,
            textAlign: 'center',
            fontSize: 13,
            color: colors.fg2,
            lineHeight: 19,
          }}
        >
          Sync Payoneer or upload a CSV to see spending here.
        </Text>
      </Card>
    );
  }
  const cats = [
    { name: 'Rent', amt: 350, pct: 100 },
    { name: 'Groceries', amt: 412, pct: 100 },
    { name: 'Eating out', amt: 218, pct: 53 },
    { name: 'Transport', amt: 96, pct: 23 },
    { name: 'Subs', amt: 88, pct: 21 },
  ];
  return (
    <Card>
      <SectionLabel
        right={
          <Text
            style={{
              fontFamily: typography.mono.fontFamily,
              fontSize: 13,
              color: colors.fg1,
              fontWeight: '600',
            }}
          >
            €1,284
          </Text>
        }
      >
        This month
      </SectionLabel>
      <View style={{ gap: 8 }}>
        {cats.map((c) => (
          <View key={c.name}>
            <View style={{ flexDirection: 'row', marginBottom: 4 }}>
              <Text style={{ flex: 1, fontSize: 12, color: colors.fg2 }}>{c.name}</Text>
              <Text
                style={{
                  fontFamily: typography.mono.fontFamily,
                  fontSize: 12,
                  color: colors.fg3,
                }}
              >
                €{c.amt}
              </Text>
            </View>
            <View
              style={{
                height: 4,
                backgroundColor: colors.bg3,
                borderRadius: 2,
                overflow: 'hidden',
              }}
            >
              <View style={{ width: `${c.pct}%`, height: '100%', backgroundColor: tint }} />
            </View>
          </View>
        ))}
      </View>
      <InsightTip tint={tint}>Subs up €12 vs March — Notion went to plus.</InsightTip>
    </Card>
  );
}

function HomeBody({ tint: _tint, connected }: { tint: string; connected: Set<string> }) {
  const { colors } = useTheme();
  if (!connected.has('ha')) {
    return (
      <Card>
        <Text
          style={{
            paddingVertical: 20,
            paddingHorizontal: 8,
            textAlign: 'center',
            fontSize: 13,
            color: colors.fg2,
            lineHeight: 19,
          }}
        >
          Add a Home Assistant token in Settings to control scenes here.
        </Text>
      </Card>
    );
  }
  const scenes = ['Focus', 'Wind down', 'Movie', 'All off'];
  return (
    <Card>
      <SectionLabel
        right={
          <Pill tone="success" size="sm">
            All quiet
          </Pill>
        }
      >
        State
      </SectionLabel>
      <View style={rowGap16}>
        <StatRow label="Living" value="21.4" unit="°C" />
        <StatRow label="Bedroom" value="19.8" unit="°C" />
        <StatRow label="Lights" value="4" unit="on" />
      </View>
      <View style={{ height: 14 }} />
      <SectionLabel>Scenes</SectionLabel>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {scenes.map((s) => (
          <View
            key={s}
            style={{
              paddingHorizontal: 14,
              paddingVertical: 8,
              backgroundColor: colors.bg3,
              borderRadius: 999,
              borderWidth: 1,
              borderColor: colors.borderSoft,
            }}
          >
            <Text style={{ fontSize: 12.5, color: colors.fg1 }}>{s}</Text>
          </View>
        ))}
      </View>
    </Card>
  );
}

const rowGap16 = { flexDirection: 'row' as const, gap: 16 };

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingTop: 4,
    paddingBottom: 24,
  },
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingVertical: 6,
    alignSelf: 'flex-start',
  },
  hero: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    paddingTop: 14,
    paddingBottom: 18,
    paddingHorizontal: 4,
  },
  heroAvatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 8,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  listRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 10,
  },
});
