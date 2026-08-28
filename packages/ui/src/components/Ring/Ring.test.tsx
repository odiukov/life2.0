import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { Ring } from './index';

test('renders ring with label', () => {
  render(
    <ThemeProvider>
      <Ring pct={82} color="#5b8ef5" label="82" sub="READY" testID="ring" />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('ring')).toBeOnTheScreen();
  expect(screen.getByText('82')).toBeOnTheScreen();
  expect(screen.getByText('READY')).toBeOnTheScreen();
});

test('renders ring with gradient without crashing', () => {
  render(
    <ThemeProvider>
      <Ring
        pct={80}
        color="#4ade80"
        label="80"
        sub="READY"
        gradientColors={['#0a3d10', '#30d060']}
        testID="ring-grad"
      />
    </ThemeProvider>,
  );
  expect(screen.getByTestId('ring-grad')).toBeOnTheScreen();
  expect(screen.getByText('80')).toBeOnTheScreen();
});
