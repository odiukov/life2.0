import { Pressable, Text, View } from 'react-native';
import { Screen, useTheme } from '@life-agents/ui';

export function PermissionsSlide({ onNext }: { onNext: () => void }) {
  const { colors, typography, spacing, radius } = useTheme();
  const row = {
    marginTop: spacing.s3,
    backgroundColor: colors.bg2,
    borderColor: colors.border,
    borderWidth: 1,
    paddingHorizontal: spacing.s5,
    paddingVertical: spacing.s4,
    borderRadius: radius.rMd,
  };
  return (
    <Screen>
      <View style={{ flex: 1, padding: spacing.s6, justifyContent: 'center' }}>
        <Text style={[typography.title1, { color: colors.fg1, marginBottom: spacing.s4, textAlign: 'center' }]}>
          Let us connect to your data
        </Text>
        <Pressable onPress={onNext} style={row}>
          <Text style={[typography.bodyEm, { color: colors.fg1 }]}>Connect Apple Health</Text>
          <Text style={[typography.caption, { color: colors.fg2, marginTop: spacing.s1 }]}>
            We read sleep, HR, workouts — never write.
          </Text>
        </Pressable>
        <Pressable onPress={onNext} style={row}>
          <Text style={[typography.bodyEm, { color: colors.fg1 }]}>Enable notifications</Text>
          <Text style={[typography.caption, { color: colors.fg2, marginTop: spacing.s1 }]}>
            Morning brief + critical alerts.
          </Text>
        </Pressable>
        <Pressable onPress={onNext} style={{ marginTop: spacing.s6, alignSelf: 'center' }}>
          <Text style={[typography.caption, { color: colors.fg2 }]}>Skip for now</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
