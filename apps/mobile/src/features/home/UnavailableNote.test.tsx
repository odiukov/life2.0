import { render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { UnavailableNote } from './UnavailableNote';
let mockLocale = 'en';
jest.mock('@/lib/locale', () => ({ appLocale: () => mockLocale }));
beforeEach(() => {
  mockLocale = 'en';
});
test('renders nothing when all agents are available', () => {
  render(
    <ThemeProvider>
      <UnavailableNote agents={[]} />
    </ThemeProvider>,
  );
  expect(screen.queryByTestId('home-unavailable')).toBeNull();
});
test('singular and plural labels', () => {
  const view = render(
    <ThemeProvider>
      <UnavailableNote agents={['sleep']} />
    </ThemeProvider>,
  );
  expect(screen.getByText('Sleep is unavailable right now — its card is hidden.')).toBeTruthy();
  view.rerender(
    <ThemeProvider>
      <UnavailableNote agents={['sleep', 'workout']} />
    </ThemeProvider>,
  );
  expect(
    screen.getByText('Sleep, Workout are unavailable right now — their cards are hidden.'),
  ).toBeTruthy();
});

test('Russian unavailable notes localize agent names', () => {
  mockLocale = 'ru';
  render(
    <ThemeProvider>
      <UnavailableNote agents={['sleep', 'workout']} />
    </ThemeProvider>,
  );
  expect(screen.getByText('Сон, Тренировки сейчас недоступны — карточки скрыты.')).toBeTruthy();
});
