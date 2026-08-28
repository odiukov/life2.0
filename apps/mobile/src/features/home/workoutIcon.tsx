import React from 'react';
import { Icon } from '@life-agents/ui';
import Svg, { Path } from 'react-native-svg';

/**
 * Returns a typed key describing which icon should render for a given workout.
 * Exported separately from <WorkoutIcon> so the matching logic is unit-testable.
 *
 * Format: 'phosphor:<Name>' for Phosphor matches, 'custom:<key>' for inline SVGs.
 */
export function resolveWorkoutIcon(type: string, name: string): string {
  const t = (type + ' ' + name).toLowerCase();
  if (t.includes('strength') || t.includes('weight'))                                  return 'phosphor:Barbell';
  if (t.includes('hiit') || t.includes('highintensity') || t.includes('interval'))     return 'phosphor:Lightning';
  if (t.includes('cycl') || t.includes('bike') || t.includes('gravel') || t.includes('unpaved')) return 'phosphor:PersonSimpleBike';
  if (t.includes('run'))                                                                return 'phosphor:PersonSimpleRun';
  if (t.includes('walk'))                                                               return 'phosphor:PersonSimpleWalk';
  if (t.includes('swim'))                                                               return 'phosphor:PersonSimpleSwim';
  if (t.includes('box'))                                                                return 'phosphor:BoxingGlove';
  if (t.includes('yoga') || t.includes('pilates') || t.includes('mind'))                return 'phosphor:PersonSimpleTaiChi';
  if (t.includes('hik'))                                                                return 'phosphor:PersonSimpleHike';
  if (t.includes('row'))                                                                return 'custom:rowing';
  if (t.includes('snowboard'))                                                          return 'phosphor:PersonSimpleSnowboard';
  if (t.includes('ski'))                                                                return 'phosphor:PersonSimpleSki';
  if (t.includes('stair') || t.includes('climb'))                                       return 'phosphor:Stairs';
  if (t.includes('cardio') || t.includes('elliptical'))                                 return 'phosphor:Heartbeat';
  if (t.includes('soccer') || t.includes('football'))                                   return 'phosphor:SoccerBall';
  if (t.includes('basketball'))                                                         return 'phosphor:Basketball';
  if (t.includes('tennis'))                                                             return 'phosphor:TennisBall';
  if (t.includes('martial') || t.includes('karate') || t.includes('judo'))              return 'custom:martial';
  if (t.includes('dance'))                                                              return 'custom:dance';
  if (t.includes('golf'))                                                               return 'phosphor:Golf';
  return 'phosphor:Barbell';
}

// ─── Custom SVGs (Phosphor regular weight: 256 viewBox, stroke 16) ────────────

const SVG_STROKE = {
  fill: 'none' as const,
  strokeWidth: 16,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
};

function RowingIcon({ size, color }: { size: number; color: string }) {
  // Boat hull at bottom + two oars angled up-and-out from a central rower.
  return (
    <Svg width={size} height={size} viewBox="0 0 256 256">
      {/* hull */}
      <Path d="M40 176 Q128 208 216 176" stroke={color} {...SVG_STROKE} />
      {/* left oar */}
      <Path d="M48 80 L120 152" stroke={color} {...SVG_STROKE} />
      <Path d="M40 72 L60 92" stroke={color} {...SVG_STROKE} />
      {/* right oar */}
      <Path d="M208 80 L136 152" stroke={color} {...SVG_STROKE} />
      <Path d="M216 72 L196 92" stroke={color} {...SVG_STROKE} />
      {/* rower torso */}
      <Path d="M128 152 L128 112" stroke={color} {...SVG_STROKE} />
      <Path d="M128 96 m-12 0 a12 12 0 1 0 24 0 a12 12 0 1 0 -24 0" stroke={color} {...SVG_STROKE} />
    </Svg>
  );
}

function MartialIcon({ size, color }: { size: number; color: string }) {
  // Figure mid-kick: head, torso, planted leg + extended kicking leg, raised arm.
  return (
    <Svg width={size} height={size} viewBox="0 0 256 256">
      {/* head */}
      <Path d="M120 56 m-16 0 a16 16 0 1 0 32 0 a16 16 0 1 0 -32 0" stroke={color} {...SVG_STROKE} />
      {/* torso */}
      <Path d="M120 80 L116 144" stroke={color} {...SVG_STROKE} />
      {/* guard arm (raised across chest) */}
      <Path d="M116 96 L160 88" stroke={color} {...SVG_STROKE} />
      {/* striking arm (down and back) */}
      <Path d="M116 104 L72 132" stroke={color} {...SVG_STROKE} />
      {/* planted leg */}
      <Path d="M116 144 L104 208" stroke={color} {...SVG_STROKE} />
      {/* kicking leg (up and forward) */}
      <Path d="M116 144 L208 128" stroke={color} {...SVG_STROKE} />
    </Svg>
  );
}

function DanceIcon({ size, color }: { size: number; color: string }) {
  // Figure with one arm up + offset hip. Head, asymmetric arms, swayed torso.
  return (
    <Svg width={size} height={size} viewBox="0 0 256 256">
      {/* head */}
      <Path d="M128 48 m-16 0 a16 16 0 1 0 32 0 a16 16 0 1 0 -32 0" stroke={color} {...SVG_STROKE} />
      {/* torso (S-curve via two segments) */}
      <Path d="M128 72 L140 128" stroke={color} {...SVG_STROKE} />
      <Path d="M140 128 L120 168" stroke={color} {...SVG_STROKE} />
      {/* raised arm */}
      <Path d="M132 88 L184 40" stroke={color} {...SVG_STROKE} />
      {/* low arm */}
      <Path d="M132 96 L88 128" stroke={color} {...SVG_STROKE} />
      {/* legs */}
      <Path d="M120 168 L96 216" stroke={color} {...SVG_STROKE} />
      <Path d="M120 168 L152 216" stroke={color} {...SVG_STROKE} />
    </Svg>
  );
}

// ─── Public component ─────────────────────────────────────────────────────────

type Props = {
  type: string;
  name: string;
  size?: number;
  color: string;
};

export function WorkoutIcon({ type, name, size = 28, color }: Props) {
  const key = resolveWorkoutIcon(type, name);
  if (key === 'custom:rowing')  return <RowingIcon size={size} color={color} />;
  if (key === 'custom:martial') return <MartialIcon size={size} color={color} />;
  if (key === 'custom:dance')   return <DanceIcon size={size} color={color} />;
  // phosphor:<Name>
  const phosphorName = key.slice('phosphor:'.length);
  return <Icon name={phosphorName as any} size={size} color={color} />;
}
