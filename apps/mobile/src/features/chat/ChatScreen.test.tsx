import { ThemeProvider } from '@life-agents/ui';
import { render as nativeRender, waitFor } from '@testing-library/react-native';
import { ChatScreen } from './ChatScreen';
const mockRestore = jest.fn().mockResolvedValue(undefined);
const mockConversation = jest.fn((_props: unknown) => null);
jest.mock('./useTask', () => ({ useTask: () => ({ restore: mockRestore }) }));
jest.mock('../task/TaskConversation', () => ({
  TaskConversation: (props: unknown) => mockConversation(props),
}));
test('renders the conversation and restores on mount', async () => {
  render(<ChatScreen />);
  await waitFor(() => expect(mockRestore).toHaveBeenCalledTimes(1));
  expect(mockConversation).toHaveBeenCalled();
});

function render(ui: React.ReactElement) {
  return nativeRender(<ThemeProvider>{ui}</ThemeProvider>);
}
