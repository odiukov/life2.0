import React from 'react';
import { Text, View } from 'react-native';
import { useTheme } from '../../theme';

interface SectionLabelProps {
  children: React.ReactNode;
  right?: React.ReactNode;
  testID?: string;
}

export function SectionLabel({ children, right, testID }: SectionLabelProps) {
  const { colors } = useTheme();
  return (
    <View
      testID={testID}
      style={{
        flexDirection: 'row',
        alignItems: 'baseline',
        justifyContent: 'space-between',
        gap: 8,
        paddingHorizontal: 2,
        paddingBottom: 8,
      }}
    >
      <Text
        style={{
          fontSize: 11,
          color: colors.fg3,
          fontWeight: '600',
          letterSpacing: 0.5,
          textTransform: 'uppercase',
          flexShrink: 0,
        }}
      >
        {children}
      </Text>
      {right !== undefined && (
        <View
          style={{ flexShrink: 1, minWidth: 0, flexDirection: 'row', justifyContent: 'flex-end' }}
        >
          {typeof right === 'string' ? (
            <Text numberOfLines={1} style={{ fontSize: 11, color: colors.fg4, textAlign: 'right' }}>
              {right}
            </Text>
          ) : (
            right
          )}
        </View>
      )}
    </View>
  );
}
