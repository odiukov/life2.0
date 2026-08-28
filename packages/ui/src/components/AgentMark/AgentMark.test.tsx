import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AgentMark } from './index';

test('renders with background circle by default', () => {
  render(
    <ThemeProvider>
      <AgentMark agent="sleep" testID="mark" />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('mark')).toBeOnTheScreen();
});

test('renders without background when withBackground=false', () => {
  render(
    <ThemeProvider>
      <AgentMark agent="sleep" withBackground={false} testID="mark" />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('mark')).toBeOnTheScreen();
});

test('falls back to the home icon for unknown runtime agent ids', () => {
  render(
    <ThemeProvider>
      <AgentMark agent={'unknown-agent' as any} testID="mark" />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('mark')).toBeOnTheScreen();
});
