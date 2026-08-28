import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { CircularProgress } from './index';

test('CircularProgress renders with progress and color', () => {
  render(
    <ThemeProvider>
      <CircularProgress testID="progress" size={100} progress={0.5} color="#10b981" />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('progress')).toBeOnTheScreen();
});
