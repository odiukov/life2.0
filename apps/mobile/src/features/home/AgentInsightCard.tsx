import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, { FadeInDown } from 'react-native-reanimated';
import { Icon, useTheme } from '@life-agents/ui';

type Props = {
  insight: string;
  color: string;
};

export function AgentInsightCard({ insight, color }: Props) {
  const { radius, spacing, typography } = useTheme();

  if (!insight) return null;

  return (
    <Animated.View entering={FadeInDown.duration(320).delay(60)}>
      <View
        style={[
          styles.card,
          {
            backgroundColor: color + '12',
            borderColor: color + '30',
            borderRadius: radius.rMd,
            padding: spacing.s3,
            marginBottom: spacing.s3,
          },
        ]}
      >
        <View style={styles.iconWrap}>
          <Icon name="Lightbulb" size={14} color={color} weight="fill" />
        </View>
        <Text style={[typography.caption, { color, flex: 1, lineHeight: 18 }]}>
          {insight}
        </Text>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: 'row', gap: 8, alignItems: 'flex-start', borderWidth: 1 },
  iconWrap: { marginTop: 1 },
});
