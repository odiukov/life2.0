import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { AttentionCard } from './AttentionCard';

jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('react-native-gesture-handler/ReanimatedSwipeable', () => {
  const { View } = jest.requireActual('react-native');
  return {
    __esModule: true,
    default: ({
      children,
      renderRightActions,
      testID,
    }: {
      children: React.ReactNode;
      renderRightActions: () => React.ReactNode;
      testID?: string;
    }) => (
      <View testID={testID}>
        {children}
        {renderRightActions()}
      </View>
    ),
  };
});

const base = {
  agent: 'kitchen',
  id: 'kitchen:today:2026-10-16',
  rank: 0,
  text: '2 items spoil today',
  detail: 'milk, spinach',
  action: { type: 'agent' as const },
};
const ui = (node: React.ReactElement) => render(<ThemeProvider>{node}</ThemeProvider>);

test('critical: urgent tag, no hide action', () => {
  ui(
    <AttentionCard
      item={{ ...base, level: 'critical' }}
      onPress={jest.fn()}
      onDismiss={jest.fn()}
    />,
  );
  expect(screen.getByText('URGENT')).toBeTruthy();
  expect(screen.queryByTestId('attention-swipe')).toBeNull();
});

test('high: the hide action calls onDismiss with the id', () => {
  const onDismiss = jest.fn();
  ui(<AttentionCard item={{ ...base, level: 'high' }} onPress={jest.fn()} onDismiss={onDismiss} />);
  expect(screen.getByTestId('attention-swipe')).toBeTruthy();
  fireEvent.press(screen.getByText('Hide until tomorrow'));
  expect(onDismiss).toHaveBeenCalledWith('kitchen:today:2026-10-16');
});

test('tap calls onPress with the item', () => {
  const onPress = jest.fn();
  ui(<AttentionCard item={{ ...base, level: 'normal' }} onPress={onPress} onDismiss={jest.fn()} />);
  fireEvent.press(screen.getByText('2 items spoil today'));
  expect(onPress).toHaveBeenCalledWith(expect.objectContaining({ id: base.id }));
});
