import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AgentBadge } from './index';

test('renders agent id uppercase', () => {
  render(
    <ThemeProvider>
      <AgentBadge agent="recovery" />
    </ThemeProvider>,
  );
  expect(screen.getByText('RECOVERY')).toBeOnTheScreen();
});
