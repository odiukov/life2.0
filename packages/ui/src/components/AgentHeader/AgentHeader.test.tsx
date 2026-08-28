import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AgentHeader } from './index';

test('renders primary agent label uppercase', () => {
  render(
    <ThemeProvider>
      <AgentHeader primary="sleep" />
    </ThemeProvider>,
  );
  expect(screen.getByText('SLEEP')).toBeOnTheScreen();
});

test('does not render via row when consulted is empty', () => {
  render(
    <ThemeProvider>
      <AgentHeader primary="sleep" consulted={[]} />
    </ThemeProvider>,
  );
  expect(screen.queryByText('via')).toBeNull();
});

test('renders via row with chips for each consulted peer', () => {
  render(
    <ThemeProvider>
      <AgentHeader primary="sleep" consulted={['nutrition', 'workout']} />
    </ThemeProvider>,
  );
  expect(screen.getByText('via')).toBeOnTheScreen();
  expect(screen.getByText('nutrition')).toBeOnTheScreen();
  expect(screen.getByText('workout')).toBeOnTheScreen();
});
