import { useRouter } from 'expo-router';
import { WelcomeSlide } from '@/features/onboarding/slides/Welcome';
export default function Welcome() {
  const router = useRouter();
  return <WelcomeSlide onNext={() => router.push('/(auth)/sign-in')} />;
}
