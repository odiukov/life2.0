import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { CircularProgress, useTheme } from '@life-agents/ui';
import type { AgentId } from '@life-agents/ui';
import { useQueryClient } from '@tanstack/react-query';
import { AGENT_COLOR, AGENT_META } from '../dash/agentMeta';
import type { HomeAgent } from './useHomeSummary';
import { usePressScale } from '@/lib/usePressScale';
import { BodyProfileAlert } from './BodyProfileAlert';
import { BodyProfileSheet } from './BodyProfileSheet';
import { WorkoutIcon } from './workoutIcon';

type Props = {
  agentId: AgentId;
  data: HomeAgent | null;
  onPress: () => void;
};

export function AgentTile({ agentId, data, onPress }: Props) {
  const { colors, radius, spacing, typography } = useTheme();
  const { onPressIn, onPressOut, pressStyle } = usePressScale();
  const queryClient = useQueryClient();
  const color = AGENT_COLOR[agentId];
  const meta = AGENT_META[agentId];
  const hasData = data !== null;
  const progress = data?.progress ?? null;
  const pills = data?.detail
    ? data.detail.split('·').map((p) => p.trim()).filter(Boolean)
    : [];

  const showProfileAlert = agentId === 'nutrition' && hasData && progress === null;
  const [profileSheetVisible, setProfileSheetVisible] = useState(false);

  function handleProfileSaved() {
    queryClient.invalidateQueries({ queryKey: ['home-summary'] });
  }

  return (
    <>
      <Animated.View style={[styles.tile, pressStyle]}>
        <Pressable
          onPress={onPress}
          onPressIn={onPressIn}
          onPressOut={onPressOut}
          style={[
            styles.inner,
            {
              backgroundColor: colors.bg2,
              borderRadius: radius.rLg,
              borderColor: colors.border,
              borderStyle: hasData ? 'solid' : 'dashed',
              padding: spacing.s3,
            },
          ]}
        >
          <Text style={[typography.micro, { color: colors.fg3, marginBottom: spacing.s2 }]}>
            {meta.name}
          </Text>

          {hasData ? (
            <>
              {showProfileAlert ? (
                <BodyProfileAlert onPress={() => setProfileSheetVisible(true)} />
              ) : (
                <>
                  <View style={styles.ringRow}>
                    {progress !== null ? (
                      <CircularProgress size={42} progress={progress} color={color} strokeWidth={5} />
                    ) : agentId === 'workout' ? (
                      <View style={styles.workoutIcon}>
                        <WorkoutIcon
                          type={data?.workoutType ?? ''}
                          name={data?.metric ?? ''}
                          size={28}
                          color={color}
                        />
                      </View>
                    ) : null}
                    <View style={styles.metricCol}>
                      <Text style={[typography.body, { color, fontWeight: '700' }]} numberOfLines={2}>
                        {data.metric}
                      </Text>
                      {progress !== null && (
                        <Text style={[typography.micro, { color: colors.fg3 }]} numberOfLines={1}>
                          {Math.round(progress * 100)}%
                        </Text>
                      )}
                    </View>
                  </View>

                  {pills.length > 0 && (
                    <View style={[styles.pillsRow, { marginTop: spacing.s2 }]}>
                      {pills.map((pill) => (
                        <View
                          key={pill}
                          style={[styles.pill, { backgroundColor: color + '18', borderRadius: radius.rXs }]}
                        >
                          <Text style={[typography.micro, { color }]} numberOfLines={1}>
                            {pill}
                          </Text>
                        </View>
                      ))}
                    </View>
                  )}
                </>
              )}
            </>
          ) : (
            <View style={styles.emptyCol}>
              <Text style={{ fontSize: 22 }}>
                {agentId === 'sleep' ? '😴' : agentId === 'workout' ? '🏃' : agentId === 'nutrition' ? '🥗' :
                 agentId === 'mood' ? '😊' : agentId === 'habits' ? '✅' :
                 agentId === 'recovery' ? '🔋' : agentId === 'medication' ? '💊' : '💰'}
              </Text>
              <Text style={[typography.micro, { color: colors.fg3, textAlign: 'center', marginTop: 4 }]}>No data</Text>
              <Pressable
                onPress={onPress}
                style={[styles.logBtn, { backgroundColor: color, borderRadius: radius.rXs, marginTop: spacing.s2 }]}
              >
                <Text style={[typography.micro, { color: '#fff', fontWeight: '600' }]}>+ Log</Text>
              </Pressable>
            </View>
          )}
        </Pressable>
      </Animated.View>

      <BodyProfileSheet
        visible={profileSheetVisible}
        onClose={() => setProfileSheetVisible(false)}
        onSaved={handleProfileSaved}
      />
    </>
  );
}

const styles = StyleSheet.create({
  tile: { flex: 1 },
  inner: { borderWidth: 1, height: 130 },
  ringRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  workoutIcon: { width: 42, alignItems: 'center', justifyContent: 'center' },
  dot: { width: 42, height: 42, borderRadius: 21, borderWidth: 3, opacity: 0.3 },
  metricCol: { flex: 1 },
  emptyCol: { alignItems: 'center', justifyContent: 'center', flex: 1, marginTop: 8 },
  logBtn: { paddingHorizontal: 10, paddingVertical: 4 },
  pillsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4 },
  pill: { paddingHorizontal: 6, paddingVertical: 2 },
});
