import { fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { AskBar } from './index';

function renderBar(props: Partial<React.ComponentProps<typeof AskBar>> = {}) {
  return render(
    <ThemeProvider>
      <AskBar onSubmit={jest.fn()} {...props} />
    </ThemeProvider>,
  );
}

test('typing /sleep + space sets tag and clears the slash from text', () => {
  const onChange = jest.fn();
  renderBar({
    value: '',
    tag: undefined,
    onChangeText: onChange,
  });
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep ');
  expect(onChange).toHaveBeenCalledWith({ tag: 'sleep', text: '' });
});

test('renders chip when tag is set', () => {
  renderBar({ value: '', tag: 'sleep' });
  expect(screen.getByText('sleep')).toBeOnTheScreen();
});

test('chip × button clears the tag', () => {
  const onChange = jest.fn();
  renderBar({ value: 'hi', tag: 'sleep', onChangeText: onChange });
  fireEvent.press(screen.getByTestId('agent-chip-remove'));
  expect(onChange).toHaveBeenCalledWith({ tag: undefined, text: 'hi' });
});

test('submit emits { tag, text }', () => {
  const onSubmit = jest.fn();
  renderBar({ value: 'how did I sleep', tag: 'sleep', onSubmit, onChangeText: jest.fn() });
  fireEvent.press(screen.getByTestId('ask-send'));
  expect(onSubmit).toHaveBeenCalledWith({ tag: 'sleep', text: 'how did I sleep' });
});

test('typing /calendar with calendar blocked does NOT promote to chip', () => {
  const onChange = jest.fn();
  renderBar({
    value: '',
    tag: undefined,
    onChangeText: onChange,
    blockedAgents: new Set(['calendar']),
  });
  fireEvent.changeText(screen.getByTestId('ask-input'), '/calendar ');
  expect(onChange).toHaveBeenLastCalledWith({ tag: undefined, text: '/calendar ' });
});

test('typing /home with home blocked does NOT promote to chip', () => {
  const onChange = jest.fn();
  renderBar({
    value: '',
    tag: undefined,
    onChangeText: onChange,
    blockedAgents: new Set(['home']),
  });
  fireEvent.changeText(screen.getByTestId('ask-input'), '/home ');
  expect(onChange).toHaveBeenLastCalledWith({ tag: undefined, text: '/home ' });
});

test('typing /sleep with only calendar blocked still promotes to chip', () => {
  const onChange = jest.fn();
  renderBar({
    value: '',
    tag: undefined,
    onChangeText: onChange,
    blockedAgents: new Set(['calendar']),
  });
  fireEvent.changeText(screen.getByTestId('ask-input'), '/sleep ');
  expect(onChange).toHaveBeenLastCalledWith({ tag: 'sleep', text: '' });
});

test('typing /calendar without blockedAgents prop still promotes (regression)', () => {
  const onChange = jest.fn();
  renderBar({
    value: '',
    tag: undefined,
    onChangeText: onChange,
  });
  fireEvent.changeText(screen.getByTestId('ask-input'), '/calendar ');
  expect(onChange).toHaveBeenLastCalledWith({ tag: 'calendar', text: '' });
});
