import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated from 'react-native-reanimated';
import Svg, { Circle } from 'react-native-svg';
import { AgentMark, Card, type AgentId, Icon, Screen, useTheme } from '@life-agents/ui';
import { useSubscription, type PackId } from './useSubscription';

const TOKEN_PACKS: {
  id: PackId;
  name: string;
  tokens: number;
  price: string;
  perToken: string;
  blurb: string;
  badge: string | null;
}[] = [
  {
    id: 'spark',
    name: 'Spark',
    tokens: 500,
    price: '$2.99',
    perToken: '0.60¢',
    blurb: 'A light week of check-ins.',
    badge: null,
  },
  {
    id: 'flow',
    name: 'Flow',
    tokens: 2000,
    price: '$8.99',
    perToken: '0.45¢',
    blurb: 'Most people land here.',
    badge: 'Best value',
  },
  {
    id: 'deep',
    name: 'Deep',
    tokens: 6000,
    price: '$19.99',
    perToken: '0.33¢',
    blurb: 'Long planning sessions, full days of voice.',
    badge: null,
  },
];

const TOKEN_USAGE: { agent: AgentId; label: string; action: string; cost: number }[] = [
  { agent: 'sleep', label: 'Sleep', action: 'Sleep analysis', cost: 8 },
  { agent: 'workout', label: 'Training', action: "Plan today's session", cost: 12 },
  { agent: 'nutrition', label: 'Nutrition', action: 'Log meal & macros', cost: 6 },
  { agent: 'mood', label: 'Mood', action: 'Quick journal reflection', cost: 10 },
  { agent: 'recovery', label: 'Recovery', action: 'Readiness deep-dive', cost: 18 },
  { agent: 'finance', label: 'Finance', action: 'Spending summary', cost: 14 },
];

const LIFE_PLUS_FEATURES = [
  'Unused tokens roll over up to 5,000',
  'Priority voice agent queue',
  'Unlimited integrations & history',
  'Early access to new agents',
];

function TokenGlyph({ size = 16, color }: { size?: number; color?: string }) {
  const { colors } = useTheme();
  const c = color ?? colors.accent;
  const half = size / 2;
  return (
    <Svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <Circle
        cx={half}
        cy={half}
        r={size * 0.375}
        fill="none"
        stroke={c}
        strokeWidth={size * 0.063}
      />
      <Circle
        cx={half}
        cy={half}
        r={size * 0.208}
        fill="none"
        stroke={c}
        strokeWidth={size * 0.063}
        opacity={0.55}
      />
      <Circle cx={half} cy={half} r={size * 0.067} fill={c} />
    </Svg>
  );
}

function BalanceRing({ used, total, size = 132 }: { used: number; total: number; size?: number }) {
  const { colors } = useTheme();
  const stroke = 8;
  const r = (size - stroke) / 2;
  const circumference = 2 * Math.PI * r;
  const pct = Math.min(1, used / total);
  const remaining = total - used;
  const half = size / 2;

  return (
    <View style={{ width: size, height: size }}>
      <Svg width={size} height={size} style={{ transform: [{ rotate: '-90deg' }] }}>
        <Circle cx={half} cy={half} r={r} fill="none" stroke={colors.bg3} strokeWidth={stroke} />
        <Circle
          cx={half}
          cy={half}
          r={r}
          fill="none"
          stroke={colors.accent}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${circumference * (1 - pct)} ${circumference * pct}`}
        />
      </Svg>
      <View style={StyleSheet.absoluteFill} pointerEvents="none">
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
          <Text
            style={{
              fontSize: 28,
              fontWeight: '700',
              letterSpacing: -0.8,
              color: colors.fg1,
              lineHeight: 32,
            }}
          >
            {remaining.toLocaleString()}
          </Text>
          <Text
            style={{ fontSize: 10.5, color: colors.fg3, fontWeight: '600', letterSpacing: 0.2 }}
          >
            of {total.toLocaleString()} left
          </Text>
        </View>
      </View>
    </View>
  );
}

export function SubscriptionScreen() {
  return (
    <Screen>
      <SubscriptionContent />
    </Screen>
  );
}

type SubscriptionContentProps = {
  onScroll?: React.ComponentProps<typeof Animated.ScrollView>['onScroll'];
  scrollEventThrottle?: number;
};

export function SubscriptionContent({
  onScroll,
  scrollEventThrottle,
}: SubscriptionContentProps = {}) {
  const { colors, spacing, typography, radius } = useTheme();
  const sub = useSubscription();
  const [selectedPack, setSelectedPack] = useState<PackId>('flow');
  const planActive = sub.plan.active;

  const selected = TOKEN_PACKS.find((p) => p.id === selectedPack)!;

  return (
    <Animated.ScrollView
      testID="subscription-scroll"
      onScroll={onScroll}
      scrollEventThrottle={scrollEventThrottle}
      contentContainerStyle={{ padding: spacing.s4, paddingBottom: spacing.s8, gap: spacing.s5 }}
    >
      {/* Title */}
      <View>
        <Text style={[typography.title1, { color: colors.fg1, marginBottom: spacing.s1 }]}>
          Tokens & subscription
        </Text>
        <Text style={[typography.body, { color: colors.fg3 }]}>
          Tokens fuel every conversation with your agents. Top up any time, or get a monthly
          allowance with Life+.
        </Text>
      </View>

      {/* Balance hero */}
      <View
        style={[
          styles.heroCard,
          { backgroundColor: colors.bg2, borderColor: colors.border, borderRadius: radius.rXl },
        ]}
      >
        <View style={styles.heroRow}>
          <BalanceRing used={sub.balance.used} total={sub.balance.total} />
          <View style={styles.heroRight}>
            <View style={styles.balanceLabel}>
              <TokenGlyph size={13} />
              <Text style={[typography.micro, { color: colors.fg3 }]}>Balance</Text>
            </View>
            <Text style={[typography.body, { color: colors.fg1, fontWeight: '600' }]}>
              At your current pace, you'll run out in about{' '}
              <Text style={{ color: colors.accent }}>9 days</Text>.
            </Text>
            <View
              style={[
                styles.monoBox,
                {
                  backgroundColor: colors.bg1,
                  borderColor: colors.borderSoft,
                  borderRadius: radius.rMd,
                },
              ]}
            >
              <Text style={[typography.mono, { color: colors.fg3, fontSize: 11 }]}>
                this week · {sub.balance.weekUsed} used
              </Text>
              <Text style={[typography.mono, { color: colors.fg3, fontSize: 11 }]}>
                renews on · {sub.balance.renewsOn}
              </Text>
            </View>
          </View>
        </View>
      </View>

      {/* Top-up section */}
      <View style={{ gap: spacing.s2 }}>
        <View style={styles.sectionHeader}>
          <Text style={[typography.micro, { color: colors.fg3 }]}>Top up</Text>
          <Text style={[typography.caption, { color: colors.fg4 }]}>one-off purchase</Text>
        </View>

        {TOKEN_PACKS.map((pack) => {
          const sel = selectedPack === pack.id;
          return (
            <Pressable
              key={pack.id}
              onPress={() => setSelectedPack(pack.id)}
              style={[
                styles.packRow,
                {
                  backgroundColor: sel ? colors.bg2 : colors.bg1,
                  borderColor: sel ? colors.accent : colors.border,
                  borderRadius: radius.rLg,
                },
              ]}
            >
              <View
                style={[
                  styles.packIcon,
                  {
                    backgroundColor: sel ? colors.accentSoft : colors.bg3,
                    borderRadius: radius.rMd,
                  },
                ]}
              >
                <TokenGlyph size={20} color={sel ? colors.accent : colors.fg2} />
              </View>
              <View style={{ flex: 1, gap: 3 }}>
                <View style={styles.packNameRow}>
                  <Text style={[typography.bodyEm, { color: colors.fg1 }]}>{pack.name}</Text>
                  <Text style={[typography.mono, { color: colors.fg2, fontSize: 11 }]}>
                    {pack.tokens.toLocaleString()} tk
                  </Text>
                  {pack.badge && (
                    <View
                      style={[
                        styles.badge,
                        { backgroundColor: colors.accent, borderRadius: radius.rXs },
                      ]}
                    >
                      <Text
                        style={{
                          fontSize: 9.5,
                          fontWeight: '700',
                          letterSpacing: 0.4,
                          textTransform: 'uppercase',
                          color: colors.accentInk,
                        }}
                      >
                        {pack.badge}
                      </Text>
                    </View>
                  )}
                </View>
                <Text style={[typography.caption, { color: colors.fg3 }]}>
                  {pack.blurb}
                  <Text style={{ color: colors.fg4 }}> · {pack.perToken}/tk</Text>
                </Text>
              </View>
              <View style={{ alignItems: 'flex-end', gap: spacing.s1 }}>
                <Text style={[typography.title2, { color: colors.fg1 }]}>{pack.price}</Text>
                <View
                  style={[
                    styles.radio,
                    {
                      borderColor: sel ? colors.accent : colors.fg4,
                      backgroundColor: sel ? colors.accent : 'transparent',
                    },
                  ]}
                >
                  {sel && <Icon name="Check" size={11} color={colors.accentInk} />}
                </View>
              </View>
            </Pressable>
          );
        })}

        <Pressable
          onPress={() => sub.purchase(selectedPack)}
          style={[styles.ctaBtn, { backgroundColor: colors.accent, borderRadius: radius.rMd }]}
        >
          <Text style={[typography.bodyEm, { color: colors.accentInk }]}>
            Buy {selected.name} · {selected.price}
          </Text>
        </Pressable>
        <Text style={[typography.caption, { color: colors.fg4, textAlign: 'center' }]}>
          Charged once via Apple Pay. Tokens never expire.
        </Text>
      </View>

      {/* Life+ subscription card */}
      <View style={{ gap: spacing.s2 }}>
        <Text style={[typography.micro, { color: colors.fg3 }]}>Subscription</Text>
        <View style={[styles.planCard, { borderColor: colors.accent, borderRadius: radius.rXl }]}>
          <View
            style={[styles.planGlow, { backgroundColor: colors.accentSoft }]}
            pointerEvents="none"
          />
          <View style={styles.planHeader}>
            <View
              style={[
                styles.lifeBadge,
                { backgroundColor: colors.accent, borderRadius: radius.rXs },
              ]}
            >
              <Text
                style={{
                  fontSize: 10,
                  fontWeight: '700',
                  letterSpacing: 0.6,
                  color: colors.accentInk,
                }}
              >
                LIFE+
              </Text>
            </View>
            {planActive && (
              <View style={styles.activeChip}>
                <View style={[styles.activeDot, { backgroundColor: colors.success }]} />
                <Text style={[typography.caption, { color: colors.success, fontWeight: '600' }]}>
                  Active
                </Text>
              </View>
            )}
          </View>
          <Text style={[typography.title1, { color: colors.fg1, marginBottom: spacing.s1 }]}>
            2,500 tokens every month
          </Text>
          <View style={[styles.priceRow, { marginBottom: spacing.s4 }]}>
            <Text
              style={{ fontSize: 26, fontWeight: '700', letterSpacing: -0.6, color: colors.accent }}
            >
              $6.99
            </Text>
            <Text style={[typography.body, { color: colors.fg3 }]}> / month · cancel anytime</Text>
          </View>
          <View style={{ gap: spacing.s2, marginBottom: spacing.s4 }}>
            {LIFE_PLUS_FEATURES.map((line) => (
              <View key={line} style={styles.featureRow}>
                <View style={[styles.checkCircle, { backgroundColor: colors.accentSoft }]}>
                  <Icon name="Check" size={11} color={colors.accent} />
                </View>
                <Text style={[typography.body, { color: colors.fg1, flex: 1 }]}>{line}</Text>
              </View>
            ))}
          </View>
          {planActive ? (
            <View
              style={[
                styles.renewBox,
                {
                  backgroundColor: colors.bg1,
                  borderColor: colors.borderSoft,
                  borderRadius: radius.rMd,
                },
              ]}
            >
              <Text style={[typography.caption, { color: colors.fg3, flex: 1 }]}>
                Renews{' '}
                <Text style={[typography.mono, { color: colors.fg2, fontSize: 12 }]}>
                  {sub.plan.renewsOn}
                </Text>{' '}
                · billed via App Store
              </Text>
              <Pressable onPress={sub.managePlan}>
                <Text style={[typography.caption, { color: colors.fg2, fontWeight: '600' }]}>
                  Manage
                </Text>
              </Pressable>
            </View>
          ) : (
            <Pressable
              onPress={() => sub.startPlan()}
              style={[styles.ctaBtn, { backgroundColor: colors.accent, borderRadius: radius.rMd }]}
            >
              <Text style={[typography.bodyEm, { color: colors.accentInk }]}>
                Start Life+ · 7 days free
              </Text>
            </Pressable>
          )}
        </View>
      </View>

      {/* What a token buys */}
      <View style={{ gap: spacing.s2 }}>
        <Text style={[typography.micro, { color: colors.fg3 }]}>What a token buys</Text>
        <Card pad={0}>
          {TOKEN_USAGE.map((row, i) => (
            <View
              key={row.agent}
              style={[
                styles.usageRow,
                i > 0 && {
                  borderTopWidth: StyleSheet.hairlineWidth,
                  borderTopColor: colors.borderSoft,
                },
              ]}
            >
              <AgentMark agent={row.agent} size={32} />
              <View style={{ flex: 1 }}>
                <Text style={[typography.body, { color: colors.fg1, fontWeight: '600' }]}>
                  {row.action}
                </Text>
                <Text style={[typography.caption, { color: colors.fg3 }]}>{row.label}</Text>
              </View>
              <View
                style={[
                  styles.tokenBadge,
                  { backgroundColor: colors.bg3, borderRadius: radius.rSm },
                ]}
              >
                <Text style={[typography.mono, { color: colors.fg2 }]}>~{row.cost}</Text>
                <TokenGlyph size={11} color={colors.fg3} />
              </View>
            </View>
          ))}
        </Card>
      </View>

      {/* Legal footer */}
      <View
        style={[
          styles.legalBox,
          { backgroundColor: colors.bg2, borderColor: colors.border, borderRadius: radius.rMd },
        ]}
      >
        <Text style={[typography.caption, { color: colors.fg3, lineHeight: 18 }]}>
          Subscriptions auto-renew unless cancelled at least 24h before the end of the period.
          Manage or cancel in App Store settings.
        </Text>
        <View style={styles.legalLinks}>
          <Text
            style={[typography.caption, { color: colors.fg4, textDecorationLine: 'underline' }]}
          >
            Terms
          </Text>
          <Text style={[typography.caption, { color: colors.fg4 }]}> · </Text>
          <Text
            style={[typography.caption, { color: colors.fg4, textDecorationLine: 'underline' }]}
          >
            Privacy
          </Text>
          <Text style={[typography.caption, { color: colors.fg4 }]}> · </Text>
          <Text
            style={[typography.caption, { color: colors.fg4, textDecorationLine: 'underline' }]}
            onPress={() => sub.restore()}
          >
            Restore purchases
          </Text>
        </View>
      </View>
    </Animated.ScrollView>
  );
}

const styles = StyleSheet.create({
  heroCard: { padding: 18, borderWidth: 1, overflow: 'hidden' },
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: 18 },
  heroRight: { flex: 1, gap: 8 },
  balanceLabel: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  monoBox: { padding: 10, borderWidth: 1, gap: 4 },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  packRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderWidth: 1 },
  packIcon: { width: 38, height: 38, alignItems: 'center', justifyContent: 'center' },
  packNameRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  badge: { paddingHorizontal: 6, paddingVertical: 2 },
  radio: {
    width: 18,
    height: 18,
    borderRadius: 9,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  ctaBtn: { paddingVertical: 14, alignItems: 'center', justifyContent: 'center' },
  planCard: { padding: 18, borderWidth: 1, overflow: 'hidden' },
  planGlow: {
    position: 'absolute',
    top: -40,
    right: -40,
    width: 180,
    height: 180,
    borderRadius: 90,
  },
  planHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  lifeBadge: { paddingHorizontal: 8, paddingVertical: 4 },
  activeChip: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  activeDot: { width: 6, height: 6, borderRadius: 3 },
  priceRow: { flexDirection: 'row', alignItems: 'baseline' },
  featureRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  checkCircle: {
    width: 18,
    height: 18,
    borderRadius: 9,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 1,
  },
  renewBox: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderWidth: 1 },
  usageRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 12 },
  tokenBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  legalBox: { padding: 12, borderWidth: 1, borderStyle: 'dashed' },
  legalLinks: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', marginTop: 8 },
});
