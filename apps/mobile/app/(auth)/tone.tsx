import { useState } from 'react';
import { useRouter } from 'expo-router';
import { ToneSlide } from '@/features/onboarding/slides/Tone';
import type { Tone } from '@/features/onboarding/OnboardingFlow';

export default function TonePage() {
  const router = useRouter();
  const [tone, setTone] = useState<Tone>('calm_coach');
  return <ToneSlide value={tone} onChange={setTone} onNext={() => router.push('/(auth)/permissions')} />;
}
