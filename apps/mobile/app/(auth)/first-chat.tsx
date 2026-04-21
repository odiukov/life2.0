import { useRouter } from 'expo-router';
import { FirstChatSlide } from '@/features/onboarding/slides/FirstChat';

export default function FirstChat() {
  const router = useRouter();
  return <FirstChatSlide tone="calm_coach" onComplete={() => router.replace('/(tabs)/chat')} />;
}
