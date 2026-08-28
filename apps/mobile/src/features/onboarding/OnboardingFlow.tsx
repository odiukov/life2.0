import React, { useState } from 'react';
import { WelcomeSlide } from './slides/Welcome';
import { SignInSlide } from './slides/SignIn';
import { ToneSlide } from './slides/Tone';
import { PermissionsSlide } from './slides/Permissions';
import { FirstChatSlide } from './slides/FirstChat';

type Tone = 'calm_coach' | 'data_literate' | 'clinical' | 'hype';

export function OnboardingFlow({ onComplete }: { onComplete: (profile: { tone: Tone }) => void }) {
  const [step, setStep] = useState(0);
  const [tone, setTone] = useState<Tone>('calm_coach');
  const next = () => setStep((s) => s + 1);
  switch (step) {
    case 0: return <WelcomeSlide onNext={next} />;
    case 1: return <SignInSlide onNext={next} />;
    case 2: return <ToneSlide value={tone} onChange={setTone} onNext={next} />;
    case 3: return <PermissionsSlide onNext={next} />;
    case 4: return <FirstChatSlide tone={tone} onComplete={() => onComplete({ tone })} />;
    default: return null;
  }
}

export type { Tone };
