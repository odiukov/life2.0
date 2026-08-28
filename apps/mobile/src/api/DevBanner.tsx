import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { apiMode, apiBaseUrl } from './client';
import { useTheme } from '@life-agents/ui';

export function DevBanner() {
  const { colors, typography, spacing } = useTheme();
  // Hidden in release builds, and opt-out in dev via EXPO_PUBLIC_HIDE_DEV_BANNER=1
  // so UI captures (see apps/mobile/.maestro) don't carry the debug chrome.
  if (!__DEV__ || process.env.EXPO_PUBLIC_HIDE_DEV_BANNER === '1') return null;
  return (
    <View
      style={[
        styles.bar,
        { backgroundColor: colors.bg3, paddingHorizontal: spacing.s3, paddingVertical: 2 },
      ]}
    >
      <Text style={[typography.micro, { color: colors.accentHi }]}>
        {apiMode === 'local' ? `DEV · ${apiBaseUrl}` : `DEV · ${apiMode.toUpperCase()}`}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({ bar: { alignItems: 'center' } });
