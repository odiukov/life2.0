import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { Sparkbars } from './index';

test('renders without crashing', () => {
  render(
    <ThemeProvider>
      <Sparkbars values={[3, 5, 4, 6, 2, 0, 8]} color="#f5804e" testID="spark" />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('spark')).toBeOnTheScreen();
});
