import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '../../theme';
import { Bubble } from './index';

test.each(['assistant', 'user'] as const)(
  'renders %s variant with plain string children',
  (variant) => {
    render(
      <ThemeProvider>
        <Bubble variant={variant}>hello</Bubble>
      </ThemeProvider>,
    );
    expect(screen.getByText('hello')).toBeOnTheScreen();
  },
);

test('assistant variant renders mixed segments with chip', () => {
  render(
    <ThemeProvider>
      <Bubble variant="assistant" segments={['try ', { tag: 'workout' }, ' for that']} />
    </ThemeProvider>,
  );
  expect(screen.getByText('try')).toBeOnTheScreen();
  expect(screen.getByText('workout')).toBeOnTheScreen();
});

test('user variant renders chip with on-user-bubble tone', () => {
  render(
    <ThemeProvider>
      <Bubble variant="user" segments={[{ tag: 'sleep' }, ' как я спал?']} />
    </ThemeProvider>,
  );
  expect(screen.getByText('sleep')).toBeOnTheScreen();
  expect(screen.getByText('как я спал?')).toBeOnTheScreen();
});
