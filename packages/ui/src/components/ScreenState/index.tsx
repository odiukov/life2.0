import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../../theme';

type Props =
  | { kind: 'loading'; skeletonCount?: number }
  | { kind: 'empty' | 'error'; title: string; body?: string; cta?: { label: string; onPress: () => void } };

export function ScreenState(props: Props) {
  const { colors, radius, spacing, typography } = useTheme();
  if (props.kind === 'loading') {
    const n = props.skeletonCount ?? 3;
    return (
      <View style={{ padding: spacing.s3, gap: spacing.s3 }}>
        {Array.from({ length: n }).map((_, i) => (
          <View
            key={i}
            testID="skeleton"
            style={{ height: 72, backgroundColor: colors.bg2, borderRadius: radius.rMd }}
          />
        ))}
      </View>
    );
  }
  return (
    <View style={[styles.center, { padding: spacing.s6 }]}>
      <Text style={[typography.title1, { color: colors.fg1, textAlign: 'center' }]}>{props.title}</Text>
      {props.body && (
        <Text
          style={[typography.body, { color: colors.fg2, textAlign: 'center', marginTop: spacing.s3 }]}
        >
          {props.body}
        </Text>
      )}
      {props.cta && (
        <Pressable
          onPress={props.cta.onPress}
          style={{
            marginTop: spacing.s5,
            backgroundColor: colors.accent,
            paddingHorizontal: spacing.s5,
            paddingVertical: spacing.s3,
            borderRadius: radius.rMd,
          }}
        >
          <Text style={[typography.bodyEm, { color: colors.bg0 }]}>{props.cta.label}</Text>
        </Pressable>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
