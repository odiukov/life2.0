import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AgentMark } from './index';

test('renders mark at default size 20', () => {
  render(
    <ThemeProvider>
      <AgentMark agent="sleep" testID="mark" />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('mark')).toBeOnTheScreen();
});
