import React from 'react';
import { ThemeProvider } from '@life-agents/ui';
import { fireEvent, render as baseRender, screen } from '@testing-library/react-native';
import { DaySwitcher } from './DaySwitcher';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
const today = new Date(2026, 9, 14, 12);

test('labels and bounds', () => {
  const onChange = jest.fn();
  const { rerender } = render(<DaySwitcher offset={0} today={today} onChange={onChange} />);
  expect(screen.getByText('Today')).toBeTruthy();
  expect(screen.getByLabelText('Next day')).toBeDisabled();
  fireEvent.press(screen.getByLabelText('Previous day'));
  expect(onChange).toHaveBeenLastCalledWith(1);
  rerender(<DaySwitcher offset={1} today={today} onChange={onChange} />);
  expect(screen.getByText('Yesterday')).toBeTruthy();
  rerender(<DaySwitcher offset={30} today={today} onChange={onChange} />);
  expect(screen.getByLabelText('Previous day')).toBeDisabled();
});

function render(ui: React.ReactElement) {
  return baseRender(ui, { wrapper: ThemeProvider });
}
