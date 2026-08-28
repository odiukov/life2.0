import React from 'react';
import { Text } from 'react-native';
import { Screen } from './index';
import { useTheme } from '../../theme';

export default { title: 'primitives/Screen', component: Screen };

export const Basic = () => {
  const { colors } = useTheme();
  return (
    <Screen>
      <Text style={{ color: colors.fg1 }}>Screen</Text>
    </Screen>
  );
};
