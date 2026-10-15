import { HouseScreen } from '@/features/house/HouseScreen';
import { ScreenFade } from '@/components/ScreenFade';

export default function HousePage() {
  return (
    <ScreenFade>
      <HouseScreen />
    </ScreenFade>
  );
}
