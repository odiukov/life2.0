import React from 'react';
import { Text, View } from 'react-native';
import { Icon } from '../Icon';
import { useTheme } from '../../theme';

interface InsightTipProps {
  children: React.ReactNode;
  tint?: string;
  testID?: string;
}

export function InsightTip({ children, tint, testID }: InsightTipProps) {
  const { colors } = useTheme();
  const sparkColor = tint ?? colors.accent;
  return (
    <View
      testID={testID}
      style={{
        marginTop: 12,
        padding: 12,
        backgroundColor: colors.bg3,
        borderRadius: 12,
        flexDirection: 'row',
        gap: 10,
        alignItems: 'flex-start',
        borderWidth: 1,
        borderColor: colors.borderSoft,
      }}
    >
      <View style={{ marginTop: 1 }}>
        <Icon name="Sparkle" size={14} color={sparkColor} weight="fill" />
      </View>
      <Text style={{ fontSize: 12.5, color: colors.fg2, flex: 1, lineHeight: 18 }}>{children}</Text>
    </View>
  );
}
