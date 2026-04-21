import { useRouter } from 'expo-router';
import { PermissionsSlide } from '@/features/onboarding/slides/Permissions';
export default function Permissions() {
  const router = useRouter();
  return <PermissionsSlide onNext={() => router.push('/(auth)/first-chat')} />;
}
