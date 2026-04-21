import { Pressable, Text, View } from 'react-native';
import { Bubble, Screen, useTheme } from '@life-agents/ui';

type Tone = 'calm_coach' | 'data_literate' | 'clinical' | 'hype';

const greetings: Record<Tone, string> = {
  calm_coach:    "Hey — tell me how you slept last night?",
  data_literate: "Let's start with your sleep — how many hours, any awakenings?",
  clinical:      "Please provide your most recent sleep data.",
  hype:          "Let's goo! Tell me about last night's sleep 💪",
};

export function FirstChatSlide({
  tone, onComplete,
}: { tone: Tone; onComplete: () => void }) {
  const { colors, typography, spacing, radius } = useTheme();
  return (
    <Screen>
      <View style={{ flex: 1, padding: spacing.s4, justifyContent: 'center' }}>
        <Bubble variant="assistant">{greetings[tone]}</Bubble>
        <Pressable
          onPress={onComplete}
          style={{
            marginTop: spacing.s6,
            backgroundColor: colors.accent,
            paddingVertical: spacing.s3,
            borderRadius: radius.rMd,
            alignItems: 'center',
          }}
        >
          <Text style={[typography.bodyEm, { color: colors.bg0 }]}>Start chatting</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
