import { Platform } from 'react-native';

const text = Platform.select({ ios: 'SF Pro Text', android: 'Inter', default: 'Inter' });
const display = Platform.select({ ios: 'SF Pro Display', android: 'Inter', default: 'Inter' });
const mono = Platform.select({ ios: 'SF Mono', android: 'JetBrainsMono', default: 'JetBrainsMono' });

export const typography = {
  display:   { fontFamily: display, fontWeight: '700' as const, fontSize: 32, lineHeight: 36 },
  title1:    { fontFamily: display, fontWeight: '600' as const, fontSize: 22, lineHeight: 28 },
  title2:    { fontFamily: display, fontWeight: '600' as const, fontSize: 17, lineHeight: 22 },
  body:      { fontFamily: text,    fontWeight: '400' as const, fontSize: 15, lineHeight: 20 },
  bodyEm:    { fontFamily: text,    fontWeight: '600' as const, fontSize: 15, lineHeight: 20 },
  caption:   { fontFamily: text,    fontWeight: '500' as const, fontSize: 12, lineHeight: 16 },
  micro:     { fontFamily: text,    fontWeight: '600' as const, fontSize: 10, lineHeight: 14, letterSpacing: 0.4, textTransform: 'uppercase' as const },
  mono:      { fontFamily: mono,    fontWeight: '500' as const, fontSize: 13, lineHeight: 18 },
} as const;

export type TypographyToken = keyof typeof typography;
