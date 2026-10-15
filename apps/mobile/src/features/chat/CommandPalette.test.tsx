import { fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { CommandPalette } from './CommandPalette';
import { matchCommands } from './commands';
jest.mock('@/lib/locale', () => ({ appLocale: () => 'ru' }));
test('kitchen command hint renders in Russian and remains selectable', () => {
  const onSelect = jest.fn();
  const items = matchCommands('/kit');
  render(
    <ThemeProvider>
      <CommandPalette items={items} onSelect={onSelect} />
    </ThemeProvider>,
  );
  expect(screen.getByText('Холодильник, морозилка и кладовая')).toBeTruthy();
  expect(screen.queryByText('Fridge, freezer and pantry')).toBeNull();
  fireEvent.press(screen.getByText('/kitchen'));
  expect(onSelect).toHaveBeenCalledWith(items[0]);
});
