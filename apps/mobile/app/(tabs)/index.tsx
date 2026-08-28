import { HomeScreen } from '@/features/home/HomeScreen';
import { ScreenFade } from '@/components/ScreenFade';

export default function HomePage() {
  return (
    <ScreenFade>
      <HomeScreen />
    </ScreenFade>
  );
}
