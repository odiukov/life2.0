import { useRouter } from 'expo-router';
import { SignInSlide } from '@/features/onboarding/slides/SignIn';
export default function SignIn() {
  const router = useRouter();
  return <SignInSlide onNext={() => router.push('/(auth)/tone')} />;
}
