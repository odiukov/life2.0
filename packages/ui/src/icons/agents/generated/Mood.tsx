import * as React from 'react';
import Svg, { Circle, Path } from 'react-native-svg';
import type { SvgProps } from 'react-native-svg';
const SvgMood = (props: SvgProps) => (
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
    <Circle cx={12} cy={12} r={9} />
    <Circle cx={9} cy={10} r={0.5} />
    <Circle cx={15} cy={10} r={0.5} />
    <Path d="M8 15c1 1.5 2.5 2 4 2s3-.5 4-2" />
  </Svg>
);
export default SvgMood;
