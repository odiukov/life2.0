import { Pressable, Text, View } from 'react-native';
import { Screen, useTheme } from '@life-agents/ui';

type Tone = 'calm_coach' | 'data_literate' | 'clinical' | 'hype';

const samples: Record<Tone, { label: string; sample: string }> = {
  calm_coach:    { label: 'Calm coach',      sample: "You had a rough night. Want to take it easy today?" },
  data_literate: { label: 'Data-literate',   sample: "HRV down 11% vs baseline, RHR up 4 bpm. Easy Z2 is the move." },
  clinical:      { label: 'Clinical',        sample: "Recovery metrics below 7-day mean. Recommend moderate-intensity exercise or rest." },
  hype:          { label: 'Hype',            sample: "Great 7h12m! Let's crush it today." },
};

export function ToneSlide({
  value, onChange, onNext,
}: {
  value: Tone;
  onChange: (t: Tone) => void;
  onNext: () => void;
}) {
  const { colors, typography, spacing, radius } = useTheme();
  return (
    <Screen>
      <View style={{ flex: 1, padding: spacing.s4 }}>
        <Text style={[typography.title1, { color: colors.fg1, marginVertical: spacing.s4 }]}>
          Pick a voice
        </Text>
        {(Object.entries(samples) as [Tone, typeof samples[Tone]][]).map(([tone, { label, sample }]) => {
          const selected = value === tone;
          return (
            <Pressable key={tone} onPress={() => onChange(tone)} style={{ marginBottom: spacing.s3 }}>
              <View
                style={{
                  backgroundColor: colors.bg2,
                  borderWidth: 1,
                  borderColor: selected ? colors.accent : colors.border,
                  borderRadius: radius.rMd,
                  padding: spacing.s4,
                }}
              >
                <Text style={[typography.bodyEm, { color: colors.fg1, marginBottom: spacing.s1 }]}>{label}</Text>
                <Text style={[typography.body, { color: colors.fg2 }]}>{sample}</Text>
              </View>
            </Pressable>
          );
        })}
        <Pressable
          onPress={onNext}
          style={{
            marginTop: spacing.s4,
            backgroundColor: colors.accent,
            paddingVertical: spacing.s3,
            borderRadius: radius.rMd,
            alignItems: 'center',
          }}
        >
          <Text style={[typography.bodyEm, { color: colors.bg0 }]}>Use this voice</Text>
        </Pressable>
      </View>
    </Screen>
  );
}
