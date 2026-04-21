import { render, screen, fireEvent } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider } from '@life-agents/ui';
import { OnboardingFlow } from './OnboardingFlow';

test('advances Welcome → Sign-in on primary CTA', () => {
  const onComplete = jest.fn();
  render(
    <SafeAreaProvider>
      <ThemeProvider>
        <OnboardingFlow onComplete={onComplete} />
      </ThemeProvider>
    </SafeAreaProvider>,
  );
  expect(screen.getByText('Your health, your money, your days — one conversation.')).toBeOnTheScreen();
  fireEvent.press(screen.getByText('Get started'));
  expect(screen.getByText('Continue with Apple')).toBeOnTheScreen();
});
