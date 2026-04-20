import * as React from 'react';
import Svg, { Rect, Circle } from 'react-native-svg';
import type { SvgProps } from 'react-native-svg';
const SvgFinance = (props: SvgProps) => (
  <Svg
    xmlns="http://www.w3.org/2000/svg"
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
    <Rect width={18} height={12} x={3} y={6} rx={2} />
    <Circle cx={12} cy={12} r={2} />
  </Svg>
);
export default SvgFinance;
