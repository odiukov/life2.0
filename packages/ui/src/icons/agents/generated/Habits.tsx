import * as React from 'react';
import Svg, { Rect } from 'react-native-svg';
import type { SvgProps } from 'react-native-svg';
const SvgHabits = (props: SvgProps) => (
  <Svg
    viewBox="0 0 24 24"
    width={24}
    height={24}
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    {...props}
  >
    <Rect width={7} height={7} x={3} y={3} rx={1} />
    <Rect width={7} height={7} x={14} y={3} rx={1} />
    <Rect width={7} height={7} x={3} y={14} rx={1} />
    <Rect width={7} height={7} x={14} y={14} rx={1} />
  </Svg>
);
export default SvgHabits;
