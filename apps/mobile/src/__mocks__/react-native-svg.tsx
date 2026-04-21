/**
 * Manual mock for react-native-svg.
 *
 * The native SVG primitives don't work in Jest/jsdom. We replace them with
 * plain React Native Views so that rendering and testID propagation work.
 */
import React from 'react';
import { View } from 'react-native';
import type { ViewProps } from 'react-native';

const Svg = ({ children, ...rest }: ViewProps) => <View {...(rest as ViewProps)}>{children}</View>;

const makeShape = (name: string) => {
  const Comp = ({ children, ...rest }: ViewProps) => <View {...rest}>{children}</View>;
  Comp.displayName = name;
  return Comp;
};

export const Path = makeShape('Path');
export const Circle = makeShape('Circle');
export const Rect = makeShape('Rect');
export const Line = makeShape('Line');
export const Polyline = makeShape('Polyline');
export const Polygon = makeShape('Polygon');
export const Ellipse = makeShape('Ellipse');
export const G = makeShape('G');
export const Defs = makeShape('Defs');
export const ClipPath = makeShape('ClipPath');
export const Use = makeShape('Use');
export const Symbol = makeShape('Symbol');
export const LinearGradient = makeShape('LinearGradient');
export const RadialGradient = makeShape('RadialGradient');
export const Stop = makeShape('Stop');
export const Mask = makeShape('Mask');
export const Pattern = makeShape('Pattern');
export const Text = makeShape('Text');
export const TSpan = makeShape('TSpan');
export const TextPath = makeShape('TextPath');
export const Image = makeShape('Image');
export const ForeignObject = makeShape('ForeignObject');
export const Marker = makeShape('Marker');

// Named Svg export for `import { Svg } from 'react-native-svg'`
export { Svg };

// Default export for `import Svg from 'react-native-svg'`
export default Svg;
