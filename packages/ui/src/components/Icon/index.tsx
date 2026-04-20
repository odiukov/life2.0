import React from 'react';
import * as Phosphor from 'phosphor-react-native';
import { useTheme } from '../../theme';

type PhosphorName = keyof typeof Phosphor;

export function Icon({
  name,
  size = 20,
  weight = 'regular',
  color,
  testID,
}: {
  name: PhosphorName;
  size?: number;
  weight?: 'thin' | 'light' | 'regular' | 'bold' | 'fill' | 'duotone';
  color?: string;
  testID?: string;
}) {
  const { colors } = useTheme();
  const Component = Phosphor[name] as React.ComponentType<{
    size?: number;
    weight?: string;
    color?: string;
    testID?: string;
  }>;
  return <Component size={size} weight={weight} color={color ?? colors.fg1} testID={testID} />;
}
