import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { Icon } from './index';

test('renders named icon at size 20 default', () => {
  render(
    <ThemeProvider>
      <Icon name="Microphone" testID="icon" />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('icon')).toBeOnTheScreen();
});
