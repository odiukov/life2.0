import React from 'react';
import { Text } from 'react-native';
import { Card } from './index';
import { useTheme } from '../../theme';

export default { title: 'primitives/Card', component: Card };

export const Basic = () => {
  const { colors } = useTheme();
  return (
    <Card>
      <Text style={{ color: colors.fg1 }}>Hello world</Text>
    </Card>
  );
};
