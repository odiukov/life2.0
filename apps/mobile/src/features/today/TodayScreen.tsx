import React from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useQuery } from '@tanstack/react-query';
import { AlertCard, Card, Screen, ScreenState, StatusPill, useTheme } from '@life-agents/ui';
import { api } from '@/api/client';

export function TodayScreen() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['today'],
    queryFn: async () => {
      const { data, error } = await api.GET('/today');
      if (error) throw error;
      return data!;
    },
  });
  const { colors, spacing, typography } = useTheme();
  if (isLoading) return <Screen><ScreenState kind="loading" skeletonCount={4} /></Screen>;
  if (isError || !data)
    return (
      <Screen>
        <ScreenState
          kind="error"
          title="Couldn't load today"
          cta={{ label: 'Retry', onPress: () => refetch() }}
        />
      </Screen>
    );
  return (
    <Screen>
      <ScrollView contentContainerStyle={{ padding: spacing.s3, gap: spacing.s3 }}>
        <Text style={[typography.display, { color: colors.fg1 }]}>{data.greeting}</Text>
        <Text style={[typography.caption, { color: colors.fg2 }]}>{data.date}</Text>
        <View style={[styles.row, { gap: spacing.s2 }]}>
          {data.status_pills.map((p, i) => (
            <StatusPill key={i} tone={p.tone as 'success' | 'warn' | 'danger' | 'neu'}>
              {p.label}
            </StatusPill>
          ))}
        </View>
        {data.must_see.map((line, i) => (
          <Card key={i}>
            <Text style={[typography.body, { color: colors.fg1 }]}>{line}</Text>
          </Card>
        ))}
        {data.alerts.map((a) => (
          <AlertCard
            key={a.id}
            title={a.title}
            body={a.body}
            tone={a.severity === 'crit' ? 'danger' : a.severity === 'warn' ? 'warn' : 'info'}
            timestamp={timeAgo(a.created_at)}
          />
        ))}
      </ScrollView>
    </Screen>
  );
}

function timeAgo(iso: string): string {
  const delta = (Date.now() - new Date(iso).getTime()) / 60000;
  if (delta < 1) return 'just now';
  if (delta < 60) return `${Math.round(delta)}m ago`;
  return `${Math.round(delta / 60)}h ago`;
}

const styles = StyleSheet.create({ row: { flexDirection: 'row', flexWrap: 'wrap' } });
