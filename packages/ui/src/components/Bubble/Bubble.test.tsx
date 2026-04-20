import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { Bubble } from './index';

test.each(['assistant', 'user', 'log', 'alert'] as const)(
  'renders %s variant without crashing',
  (variant) => {
    render(
      <ThemeProvider>
        <Bubble variant={variant}>hello</Bubble>
      </ThemeProvider>,
    );
    expect(screen.getByText('hello')).toBeOnTheScreen();
  },
);
