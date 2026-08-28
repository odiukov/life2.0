import { Pressable, Text, View } from 'react-native';
import { Screen, useTheme } from '@life-agents/ui';

export function WelcomeSlide({ onNext }: { onNext: () => void }) {
  const { colors, typography, spacing, radius } = useTheme();
  return (
    <Screen>
      <View style={{ flex: 1, justifyContent: 'center', padding: spacing.s6 }}>
        <Text style={[typography.display, { color: colors.fg1, textAlign: 'center' }]}>
          Your health, your money, your days — one conversation.
        </Text>
        <Pressable
          onPress={onNext}
          style={{
            marginTop: spacing.s8,
            backgroundColor: colors.accent,
            paddingHorizontal: spacing.s6,
            paddingVertical: spacing.s4,
            borderRadius: radius.rMd,
            alignSelf: 'center',
          }}
        >
          <Text style={[typography.bodyEm, { color: colors.bg0 }]}>Get started</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
