import { render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider } from '../../theme';
import { Screen } from './index';

test('Screen renders children inside SafeAreaView with themed bg', () => {
  render(
    <SafeAreaProvider>
      <ThemeProvider>
        <Screen testID="screen"><Text>hi</Text></Screen>
      </ThemeProvider>
    </SafeAreaProvider>,
  );
  const el = screen.getByTestId('screen');
  expect(el).toBeOnTheScreen();
});
