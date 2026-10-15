import { MeScreen } from '@/features/me/MeScreen';
import { ScreenFade } from '@/components/ScreenFade';

export default function HomePage() {
  return (
    <ScreenFade>
      <MeScreen />
    </ScreenFade>
  );
}
