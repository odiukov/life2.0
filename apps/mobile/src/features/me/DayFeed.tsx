import React from 'react';
import { Pressable, Text, View } from 'react-native';
import { ScreenState, agentSolid, useTheme, type AgentId } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { isAgentId } from '../agents/agentStatusRules';
import type { DayFeedData } from './useDayFeed';

type Props = {
  feed: DayFeedData | undefined;
  loading: boolean;
  error: boolean;
  onRetry: () => void;
  onOpenAgent: (agent: AgentId) => void;
  extraUnavailable?: string[];
};

export function DayFeed({ feed, loading, error, onRetry, onOpenAgent, extraUnavailable }: Props) {
  const { colors, radius } = useTheme();
  const locale = appLocale();
  const t = useT(locale);
  if (loading) return <ScreenState kind="loading" skeletonCount={3} />;
  if (error || !feed) {
    return (
      <View style={{ gap: 8, paddingVertical: 12 }}>
        <Text style={{ color: colors.fg2 }}>{t('me.feed.error')}</Text>
        <Pressable onPress={onRetry} accessibilityRole="button">
          <Text style={{ color: colors.accentHi }}>{t('me.feed.retry')}</Text>
        </Pressable>
      </View>
    );
  }
  const unavailable = [...new Set([...feed.unavailable, ...(extraUnavailable ?? [])])].filter(
    isAgentId,
  );
  return (
    <View
      style={{
        borderLeftWidth: 2,
        borderLeftColor: colors.bg3,
        paddingLeft: 12,
        marginLeft: 4,
        gap: 12,
      }}
    >
      {feed.items.length === 0 && <Text style={{ color: colors.fg3 }}>{t('me.feed.empty')}</Text>}
      {feed.items.map((item) => {
        const agent = isAgentId(item.agent) ? item.agent : null;
        const time = new Date(item.at).toLocaleTimeString(locale, {
          hour: '2-digit',
          minute: '2-digit',
        });
        const tag = (
          <Text style={{ fontSize: 10.5, color: colors.fg3 }}>
            {time} ·{' '}
            <Text style={{ color: agent ? agentSolid(agent) : colors.fg2 }}>
              {agent ? t(`dashboard.agent_labels.${agent}`) : item.agent}
            </Text>
          </Text>
        );
        const body = (
          <Text style={{ fontSize: 13.5, color: colors.fg1, lineHeight: 19 }}>{item.text}</Text>
        );
        return (
          <Pressable
            key={item.id}
            disabled={!agent}
            onPress={() => agent && onOpenAgent(agent)}
            accessibilityRole="button"
          >
            {item.kind === 'insight' ? (
              <View
                style={{
                  marginLeft: -14,
                  padding: 12,
                  borderRadius: radius.rMd,
                  borderWidth: 1,
                  borderColor: colors.accentBorder,
                  backgroundColor: colors.bg2,
                  gap: 4,
                }}
              >
                <Text
                  style={{
                    fontSize: 10,
                    letterSpacing: 0.8,
                    color: colors.accentHi,
                    fontWeight: '700',
                  }}
                >
                  {t('me.insight')}
                </Text>
                {body}
                {tag}
              </View>
            ) : (
              <View style={{ gap: 2 }}>
                {tag}
                {body}
              </View>
            )}
          </Pressable>
        );
      })}
      {unavailable.length > 0 && (
        <Text style={{ color: colors.fg3, fontSize: 12 }}>
          {t('me.feed.unavailable', {
            agents: unavailable.map((a) => t(`dashboard.agent_labels.${a}`)).join(', '),
            count: unavailable.length,
          })}
        </Text>
      )}
    </View>
  );
}
