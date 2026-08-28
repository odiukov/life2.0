import React from 'react';
import { StyleSheet, View, ViewProps } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../../theme';

type Props = ViewProps & { edges?: ('top' | 'bottom' | 'left' | 'right')[] };

export function Screen({ children, style, edges = ['top', 'bottom'], ...rest }: Props) {
  const { colors } = useTheme();
  return (
    <SafeAreaView edges={edges} style={[styles.safe, { backgroundColor: colors.bg0 }, style]} {...rest}>
      <View style={styles.inner}>{children}</View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  inner: { flex: 1 },
  safe: { flex: 1 },
});
