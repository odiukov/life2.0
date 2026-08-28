import { render, screen, fireEvent } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AgentChip } from './index';

test('renders agent name in lowercase by default', () => {
  render(
    <ThemeProvider>
      <AgentChip agent="sleep" />
    </ThemeProvider>,
  );
  expect(screen.getByText('sleep')).toBeOnTheScreen();
});

test('removable variant fires onRemove when × pressed', () => {
  const onRemove = jest.fn();
  render(
    <ThemeProvider>
      <AgentChip agent="sleep" tone="on-input" removable onRemove={onRemove} />
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByTestId('agent-chip-remove'));
  expect(onRemove).toHaveBeenCalledTimes(1);
});

test('non-removable does not render the × button', () => {
  render(
    <ThemeProvider>
      <AgentChip agent="sleep" tone="on-bubble" />
    </ThemeProvider>,
  );
  expect(screen.queryByTestId('agent-chip-remove')).toBeNull();
});
