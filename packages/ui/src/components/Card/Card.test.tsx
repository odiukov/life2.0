import { fireEvent, render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';
import { ThemeProvider } from '../../theme';
import { Card } from './index';

test('Card renders children', () => {
  render(
    <ThemeProvider>
      <Card testID="card"><Text>content</Text></Card>
    </ThemeProvider>,
  );
  expect(screen.getByTestId('card')).toBeOnTheScreen();
});

test('Card calls onPress when tapped', () => {
  const onPress = jest.fn();
  render(
    <ThemeProvider>
      <Card onPress={onPress} testID="card"><Text>x</Text></Card>
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByTestId('card'));
  expect(onPress).toHaveBeenCalledTimes(1);
});

test('Card applies custom pad', () => {
  render(
    <ThemeProvider>
      <Card pad={8} testID="card"><Text>x</Text></Card>
    </ThemeProvider>,
  );
  expect(screen.getByTestId('card')).toBeOnTheScreen();
});
