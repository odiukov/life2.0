import { render, screen, fireEvent } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AgentCard } from './index';

test('calls onPress with agent id', () => {
  const onPress = jest.fn();
  render(
    <ThemeProvider>
      <AgentCard agent="sleep" label="Sleep" metric="7h12m" tint="success" onPress={onPress} />
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByTestId('agent-card-sleep'));
  expect(onPress).toHaveBeenCalledWith('sleep');
});
