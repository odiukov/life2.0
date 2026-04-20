import { render, screen, fireEvent } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AlertCard } from './index';

test('fires onPress', () => {
  const onPress = jest.fn();
  render(
    <ThemeProvider>
      <AlertCard title="Missed B12 for 2d" body="2 consecutive days without log" tone="warn" timestamp="2h ago" onPress={onPress} />
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByTestId('alert-card'));
  expect(onPress).toHaveBeenCalled();
});
