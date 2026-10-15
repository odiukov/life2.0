import React from 'react';
import { Text, View } from 'react-native';
import { useTheme } from '@life-agents/ui';

export function ErrorBubble({ message }: { message: string }) {
  const { colors, spacing, radius, typography } = useTheme();
  return (
    <View
      testID="chat-error"
      accessibilityRole="alert"
      style={{
        borderColor: colors.danger,
        borderWidth: 1,
        padding: spacing.s3,
        borderRadius: radius.rMd,
      }}
    >
      <Text style={[typography.body, { color: colors.danger }]}>⚠️ {message}</Text>
    </View>
  );
}
