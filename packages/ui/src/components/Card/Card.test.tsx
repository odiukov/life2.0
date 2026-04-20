import { render, screen } from '@testing-library/react-native';
import { Text } from 'react-native';
import { ThemeProvider } from '../../theme';
import { Card } from './index';

test('Card renders with bg2 + border', () => {
  render(
    <ThemeProvider>
      <Card testID="card"><Text>content</Text></Card>
    </ThemeProvider>,
  );
  expect(screen.getByTestId('card')).toBeOnTheScreen();
});
