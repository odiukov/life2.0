import React from 'react';
import { Pressable, StyleSheet, Text } from 'react-native';
import { useTheme } from '@life-agents/ui';

type Props = {
  onPress: () => void;
};

export function BodyProfileAlert({ onPress }: Props) {
  const { typography } = useTheme();
  return (
    <Pressable style={styles.banner} onPress={onPress}>
      <Text style={[typography.micro, styles.text]}>
        ⚠︎ Set up body profile →
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    marginTop: 7,
    borderRadius: 7,
    paddingVertical: 5,
    paddingHorizontal: 7,
    backgroundColor: 'rgba(245,158,11,0.12)',
    borderWidth: 1,
    borderColor: 'rgba(245,158,11,0.3)',
  },
  text: {
    color: '#fbbf24',
  },
});
