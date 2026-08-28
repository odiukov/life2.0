import { Pressable, Text, View } from 'react-native';
import { Screen, useTheme } from '@life-agents/ui';

export function SignInSlide({ onNext }: { onNext: () => void }) {
  const { colors, typography, spacing, radius } = useTheme();
  const btn = {
    marginTop: spacing.s3,
    backgroundColor: colors.bg2,
    borderColor: colors.border,
    borderWidth: 1,
    paddingHorizontal: spacing.s5,
    paddingVertical: spacing.s3,
    borderRadius: radius.rMd,
    alignItems: 'center' as const,
  };
  return (
    <Screen>
      <View style={{ flex: 1, justifyContent: 'center', padding: spacing.s6 }}>
        <Text style={[typography.title1, { color: colors.fg1, marginBottom: spacing.s6, textAlign: 'center' }]}>
          Sign in to get started
        </Text>
        <Pressable onPress={onNext} style={btn}>
          <Text style={[typography.bodyEm, { color: colors.fg1 }]}>Continue with Apple</Text>
        </Pressable>
        <Pressable onPress={onNext} style={btn}>
          <Text style={[typography.bodyEm, { color: colors.fg1 }]}>Continue with Google</Text>
        </Pressable>
        <Pressable onPress={onNext} style={btn}>
          <Text style={[typography.bodyEm, { color: colors.fg1 }]}>Continue with email</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
