import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { MetricChip } from './index';

test('renders +8% with "up" variant', () => {
  render(
    <ThemeProvider>
      <MetricChip variant="up">+8%</MetricChip>
    </ThemeProvider>,
  );
  expect(screen.getByText('+8%')).toBeOnTheScreen();
});
