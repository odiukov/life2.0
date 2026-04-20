import { render, screen, fireEvent } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { ScreenState } from './index';

test('empty kind renders title + cta', () => {
  const onPress = jest.fn();
  render(
    <ThemeProvider>
      <ScreenState kind="empty" title="No data yet" cta={{ label: 'Connect', onPress }} />
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByText('Connect'));
  expect(onPress).toHaveBeenCalled();
});

test('error kind shows retry', () => {
  const onRetry = jest.fn();
  render(
    <ThemeProvider>
      <ScreenState kind="error" title="Oops" cta={{ label: 'Retry', onPress: onRetry }} />
    </ThemeProvider>,
  );
  fireEvent.press(screen.getByText('Retry'));
  expect(onRetry).toHaveBeenCalled();
});

test('loading kind renders skeleton count', () => {
  render(
    <ThemeProvider>
      <ScreenState kind="loading" skeletonCount={3} />
    </ThemeProvider>,
  );
  expect(screen.getAllByTestId('skeleton')).toHaveLength(3);
});
