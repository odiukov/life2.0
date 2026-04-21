/**
 * Manual mock for react-native-safe-area-context.
 *
 * SafeAreaView and SafeAreaProvider use native modules that don't work in
 * the Jest/jsdom environment. We replace them with plain Views so that
 * testID / children propagate correctly.
 */
import React from 'react';
import { View } from 'react-native';
import type { ViewProps } from 'react-native';

const MOCK_INSETS = { top: 0, right: 0, bottom: 0, left: 0 };
const MOCK_FRAME = { x: 0, y: 0, width: 320, height: 640 };

const SafeAreaView = ({ children, style, ...rest }: ViewProps) => (
  <View style={style} {...rest}>{children}</View>
);

const SafeAreaProvider = ({ children }: { children?: React.ReactNode }) => (
  <>{children}</>
);

const useSafeAreaInsets = () => MOCK_INSETS;
const useSafeAreaFrame = () => MOCK_FRAME;

const initialWindowMetrics = { insets: MOCK_INSETS, frame: MOCK_FRAME };

module.exports = {
  SafeAreaView,
  SafeAreaProvider,
  useSafeAreaInsets,
  useSafeAreaFrame,
  initialWindowMetrics,
};
