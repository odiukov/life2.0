import * as React from 'react';
import Svg, { Rect, Path } from 'react-native-svg';
import type { SvgProps } from 'react-native-svg';
const SvgMedication = (props: SvgProps) => (
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
    <Rect width={18} height={8} x={3} y={8} rx={4} />
    <Path d="M12 8v8" />
  </Svg>
);
export default SvgMedication;
