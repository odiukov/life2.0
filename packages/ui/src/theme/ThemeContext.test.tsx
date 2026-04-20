import { render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';
import { ThemeProvider, useTheme } from './index';

function Probe() {
  const { mode, colors } = useTheme();
  return <Text testID="probe">{mode}:{colors.accent}</Text>;
}

test('defaults to dark theme with teal accent', () => {
  render(
    <ThemeProvider>
      <Probe />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('probe')).toHaveTextContent('dark:#06b6d4');
});

test('honors explicit mode prop', () => {
  render(
    <ThemeProvider mode="light">
      <Probe />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('probe')).toHaveTextContent('light:#0891b2');
});
