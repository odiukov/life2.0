import { render, screen, fireEvent } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AskBar } from './index';

test('calls onSubmit when user types and presses send', () => {
  const onSubmit = jest.fn();
  render(
    <ThemeProvider>
      <AskBar onSubmit={onSubmit} />
    </ThemeProvider>,
  );
  fireEvent.changeText(screen.getByPlaceholderText('Ask or log…'), 'hello');
  fireEvent.press(screen.getByTestId('ask-send'));
  expect(onSubmit).toHaveBeenCalledWith('hello');
});

test('calls onVoice when mic pressed', () => {
  const onVoice = jest.fn();
  render(
    <ThemeProvider>
      <AskBar onSubmit={() => {}} onVoice={onVoice} />
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByTestId('ask-mic'));
  expect(onVoice).toHaveBeenCalled();
});
