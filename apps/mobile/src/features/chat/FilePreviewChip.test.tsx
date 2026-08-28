import { render, screen, fireEvent } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { FilePreviewChip } from './FilePreviewChip';

function wrap(ui: React.ReactElement) {
  return render(<ThemeProvider>{ui}</ThemeProvider>);
}

test('renders filename', () => {
  wrap(<FilePreviewChip fileName="ViHealth_2026-04.pdf" onDismiss={() => {}} />);
  expect(screen.getByText('ViHealth_2026-04.pdf')).toBeOnTheScreen();
});

test('calls onDismiss when × pressed', () => {
  const onDismiss = jest.fn();
  wrap(<FilePreviewChip fileName="test.pdf" onDismiss={onDismiss} />);
  fireEvent.press(screen.getByTestId('file-chip-dismiss'));
  expect(onDismiss).toHaveBeenCalledTimes(1);
});
