import * as React from 'react';
import Svg, { Rect, Path } from 'react-native-svg';
import type { SvgProps } from 'react-native-svg';
const SvgCalendar = (props: SvgProps) => (
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
    <Rect width={18} height={16} x={3} y={5} rx={2} />
    <Path d="M8 3v4m8-4v4M3 10h18" />
  </Svg>
);
export default SvgCalendar;
