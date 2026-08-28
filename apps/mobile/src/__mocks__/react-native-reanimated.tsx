// Jest mock for react-native-reanimated (v4)
// Provides minimal CJS stubs so components using Reanimated can be tested without
// native modules or ESM transform issues.
import type { ComponentType, ReactNode } from 'react';

const ReactRuntime = require('react');
const { ScrollView, View } = require('react-native');

const NOOP = () => {};
const ID = (x: unknown) => x;

function useSharedValue(init: unknown) {
  const ref = ReactRuntime.useRef(init);
  return {
    get value() {
      return ref.current;
    },
    set value(v: unknown) {
      ref.current = v;
    },
  };
}

function useAnimatedStyle(fn: () => object) {
  return fn();
}

const withTiming = (_toValue: unknown, _config?: unknown, callback?: (finished: boolean) => void) => {
  if (callback) callback(true);
  return _toValue;
};

const withSpring = (_toValue: unknown, _config?: unknown, callback?: (finished: boolean) => void) => {
  if (callback) callback(true);
  return _toValue;
};

const Easing = {
  out: ID,
  in: ID,
  inOut: ID,
  ease: ID,
  linear: ID,
  quad: ID,
  cubic: ID,
  exp: ID,
  circle: ID,
  bounce: ID,
  back: () => ID,
  bezier: () => ID,
  poly: () => ID,
  elastic: () => ID,
};

function AnimatedView({
  style,
  children,
  ...rest
}: {
  style?: object;
  children?: ReactNode;
  [key: string]: unknown;
}) {
  return ReactRuntime.createElement(View, { style, ...rest }, children);
}

const Animated = {
  View: AnimatedView,
  Text: ({ children, ...rest }: { children?: ReactNode; [key: string]: unknown }) =>
    ReactRuntime.createElement(View, rest, children),
  Image: ({ ...rest }: { [key: string]: unknown }) => ReactRuntime.createElement(View, rest),
  ScrollView: ({ children, ...rest }: { children?: ReactNode; [key: string]: unknown }) =>
    ReactRuntime.createElement(ScrollView, rest, children),
  createAnimatedComponent: (Component: ComponentType<unknown>) => Component,
};

module.exports = {
  default: Animated,
  useSharedValue,
  useAnimatedStyle,
  useAnimatedProps: (fn: () => object) => fn(),
  withTiming,
  withSpring,
  withDecay: NOOP,
  withRepeat: NOOP,
  withSequence: NOOP,
  withDelay: NOOP,
  cancelAnimation: NOOP,
  runOnJS: (fn: (...args: unknown[]) => unknown) => fn,
  runOnUI: (fn: (...args: unknown[]) => unknown) => fn,
  Easing,
  Animated,
  ...Animated,
};
