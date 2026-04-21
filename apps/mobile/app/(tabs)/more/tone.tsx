import { useRouter } from 'expo-router';
import { useState } from 'react';
import { ToneSlide } from '@/features/onboarding/slides/Tone';

type Tone = 'calm_coach' | 'data_literate' | 'clinical' | 'hype';

export default function ToneSettings() {
  const router = useRouter();
  const [tone, setTone] = useState<Tone>('calm_coach');
  return <ToneSlide value={tone} onChange={setTone} onNext={() => router.back()} />;
}
