import { render, screen, fireEvent, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider } from '@life-agents/ui';
import { ChatScreen } from './ChatScreen';

test('sending a message appends user bubble and streams assistant reply', async () => {
  render(
    <SafeAreaProvider>
      <ThemeProvider>
        <ChatScreen />
      </ThemeProvider>
    </SafeAreaProvider>,
  );
  fireEvent.changeText(screen.getByPlaceholderText('Ask or log…'), 'hello');
  fireEvent.press(screen.getByTestId('ask-send'));
  expect(await screen.findByText('hello')).toBeOnTheScreen();
  await waitFor(
    () => expect(screen.getByText(/Recovered/)).toBeOnTheScreen(),
    { timeout: 3000 },
  );
});
