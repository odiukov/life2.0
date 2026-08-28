import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { Pill } from './index';

test('renders neutral pill', () => {
  render(
    <ThemeProvider>
      <Pill testID="pill">WELLNESS</Pill>
    </ThemeProvider>,
  );
  expect(screen.getByTestId('pill')).toBeOnTheScreen();
});

test('renders warn pill', () => {
  render(
    <ThemeProvider>
      <Pill tone="warn" testID="pill">WARN</Pill>
    </ThemeProvider>,
  );
  expect(screen.getByTestId('pill')).toBeOnTheScreen();
});
