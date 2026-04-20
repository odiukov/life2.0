import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { StatusPill } from './index';

test('renders label', () => {
  render(
    <ThemeProvider>
      <StatusPill tone="success">Recovered</StatusPill>
    </ThemeProvider>,
  );
  expect(screen.getByText('Recovered')).toBeOnTheScreen();
});
