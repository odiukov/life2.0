import { Platform } from 'react-native';

// iOS: SF Pro handles fontWeight natively. Android: expo-google-fonts registers
// weight-baked family names (e.g. Inter_400Regular). Token values below map each
// weight to the correct Android family; `fontWeight` remains for iOS rendering
// and is redundant on Android but harmless.

const ios = { text: 'SF Pro Text', display: 'SF Pro Display', mono: 'SF Mono' };

const android = {
  text400:  'Inter_400Regular',
  text500:  'Inter_500Medium',
  text600:  'Inter_600SemiBold',
  text700:  'Inter_700Bold',
  display600: 'Inter_600SemiBold',
  display700: 'Inter_700Bold',
  mono500:  'JetBrainsMono_500Medium',
};

const text400   = Platform.select({ ios: ios.text,   android: android.text400,   default: android.text400   });
const text500   = Platform.select({ ios: ios.text,   android: android.text500,   default: android.text500   });
const text600   = Platform.select({ ios: ios.text,   android: android.text600,   default: android.text600   });
const display600 = Platform.select({ ios: ios.display, android: android.display600, default: android.display600 });
const display700 = Platform.select({ ios: ios.display, android: android.display700, default: android.display700 });
const mono500   = Platform.select({ ios: ios.mono,   android: android.mono500,   default: android.mono500   });

export const typography = {
  display:   { fontFamily: display700, fontWeight: '700' as const, fontSize: 32, lineHeight: 36 },
  title1:    { fontFamily: display600, fontWeight: '600' as const, fontSize: 22, lineHeight: 28 },
  title2:    { fontFamily: display600, fontWeight: '600' as const, fontSize: 17, lineHeight: 22 },
  body:      { fontFamily: text400,    fontWeight: '400' as const, fontSize: 15, lineHeight: 20 },
  bodyEm:    { fontFamily: text600,    fontWeight: '600' as const, fontSize: 15, lineHeight: 20 },
  caption:   { fontFamily: text500,    fontWeight: '500' as const, fontSize: 12, lineHeight: 16 },
  micro:     { fontFamily: text600,    fontWeight: '600' as const, fontSize: 10, lineHeight: 14, letterSpacing: 0.4, textTransform: 'uppercase' as const },
  mono:      { fontFamily: mono500,    fontWeight: '500' as const, fontSize: 13, lineHeight: 18 },
} as const;

export type TypographyToken = keyof typeof typography;
