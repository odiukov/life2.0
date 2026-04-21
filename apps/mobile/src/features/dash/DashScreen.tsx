import React from 'react';
import { FlatList } from 'react-native';
import { useRouter } from 'expo-router';
import { useQuery } from '@tanstack/react-query';
import { AgentCard, Screen, ScreenState, useTheme } from '@life-agents/ui';
import type { AgentId } from '@life-agents/ui';
import { api } from '@/api/client';

type AgentTint = 'success' | 'warn' | 'danger' | 'neutral';

export function DashScreen() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['dashboard'],
    queryFn: async () => {
      const { data, error } = await api.GET('/dashboard/summary');
      if (error) throw error;
      return data!;
    },
  });
  const router = useRouter();
  const { spacing } = useTheme();
  if (isLoading) return <Screen><ScreenState kind="loading" skeletonCount={4} /></Screen>;
  if (isError || !data)
    return (
      <Screen>
        <ScreenState
          kind="error"
          title="Couldn't load dashboard"
          cta={{ label: 'Retry', onPress: () => refetch() }}
        />
      </Screen>
    );
  return (
    <Screen>
      <FlatList
        data={data.agents}
        keyExtractor={(a) => a.agent}
        numColumns={2}
        columnWrapperStyle={{ gap: spacing.s3 }}
        contentContainerStyle={{ padding: spacing.s3, gap: spacing.s3 }}
        renderItem={({ item }) => (
          <AgentCard
            agent={item.agent as AgentId}
            label={item.label}
            metric={item.metric}
            tint={item.tint as AgentTint}
            onPress={(id) => router.push(`/(tabs)/dash/${id}` as never)}
          />
        )}
      />
    </Screen>
  );
}
