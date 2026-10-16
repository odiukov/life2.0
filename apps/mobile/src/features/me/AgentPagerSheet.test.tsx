import React from 'react';
import { FlatList, Text } from 'react-native';
import { ThemeProvider } from '@life-agents/ui';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { AgentPagerSheet, PAGES } from './AgentPagerSheet';
import { useTaskSheet } from '../task/sheetStore';
let mockWidth = 400;
jest.mock('react-native/Libraries/Utilities/useWindowDimensions', () => ({
  __esModule: true,
  default: () => ({ width: mockWidth, height: 800, scale: 1, fontScale: 1 }),
}));
jest.mock('@/lib/locale', () => ({ appLocale: () => 'en' }));
jest.mock('../home/AgentDetailContent', () => ({
  AgentDetailContent: ({
    agentId,
    enabled,
    onAction,
  }: {
    agentId: string;
    enabled: boolean;
    onAction: (m: string) => void;
  }) => {
    return (
      <Text onPress={() => onAction('analyze my week')}>{`detail:${agentId}:${enabled}`}</Text>
    );
  },
}));
jest.mock('../kitchen/KitchenScreen', () => ({
  KitchenPanel: () => <Text>kitchen-panel</Text>,
}));
jest.mock('./AllAgentsGrid', () => ({
  AllAgentsGrid: ({ onPick }: { onPick: (id: string) => void }) => {
    return (
      <>
        <Text onPress={() => onPick('nutrition')}>grid</Text>
        <Text onPress={() => onPick('body')}>body</Text>
      </>
    );
  },
}));
const wrap = (
  start: React.ComponentProps<typeof AgentPagerSheet>['start'],
  onClose = jest.fn(),
  onPickOther = jest.fn(),
) => (
  <ThemeProvider>
    <AgentPagerSheet start={start} onClose={onClose} onPickOther={onPickOther} />
  </ThemeProvider>
);
test('grid first, only agents with details, arrows and swipe select one enabled page', () => {
  expect(PAGES[0]).toBe('all');
  expect(PAGES).not.toContain('body');
  render(wrap('sleep'));
  expect(screen.getByText('detail:sleep:true')).toBeTruthy();
  fireEvent.press(screen.getByLabelText('Next agent'));
  expect(screen.getByText('detail:workout:true')).toBeTruthy();
  expect(screen.getByText('detail:sleep:false')).toBeTruthy();
  fireEvent.press(screen.getByLabelText('Previous agent'));
  expect(screen.getByText('detail:sleep:true')).toBeTruthy();
  const pager = screen.getByTestId('agent-pager');
  fireEvent(pager, 'momentumScrollEnd', {
    nativeEvent: { contentOffset: { x: pager.props.getItemLayout(null, 4).offset } },
  });
  expect(screen.getByText('detail:nutrition:true')).toBeTruthy();
});
test('grid jumps, action closes and preserves agent context, unsupported agent dispatches', () => {
  jest.useFakeTimers();
  const close = jest.fn();
  const other = jest.fn();
  render(wrap('all', close, other));
  fireEvent.press(screen.getByText('body'));
  expect(other).toHaveBeenCalledWith('body');
  fireEvent.press(screen.getByText('grid'));
  fireEvent.press(screen.getByText('detail:nutrition:true'));
  act(() => jest.runAllTimers());
  expect(close).toHaveBeenCalled();
  expect(useTaskSheet.getState().pending).toEqual({ lead: 'nutrition', send: 'analyze my week' });
  jest.useRealTimers();
});
test('actual scroll position follows changes, layout and reopen', () => {
  const scroll = jest.spyOn(FlatList.prototype, 'scrollToOffset').mockImplementation(() => {});
  const result = render(wrap('sleep'));
  const width = screen.getByTestId('agent-pager').props.getItemLayout(null, 1).length;
  expect(scroll).toHaveBeenLastCalledWith({
    offset: PAGES.indexOf('sleep') * width,
    animated: false,
  });
  result.rerender(wrap('nutrition'));
  expect(scroll).toHaveBeenLastCalledWith({
    offset: PAGES.indexOf('nutrition') * width,
    animated: false,
  });
  result.rerender(wrap(null));
  result.rerender(wrap('sleep'));
  fireEvent(screen.getByTestId('agent-pager'), 'layout', {
    nativeEvent: { layout: { width, height: 600, x: 0, y: 0 } },
  });
  expect(scroll).toHaveBeenLastCalledWith({
    offset: PAGES.indexOf('sleep') * width,
    animated: false,
  });
  scroll.mockRestore();
});

test.each(['arrow', 'swipe'] as const)(
  'width changes preserve the page selected by %s',
  (navigation) => {
    mockWidth = 400;
    const scroll = jest.spyOn(FlatList.prototype, 'scrollToOffset').mockImplementation(() => {});
    try {
      const result = render(wrap('sleep'));
      if (navigation === 'arrow') fireEvent.press(screen.getByLabelText('Next agent'));
      else
        fireEvent(screen.getByTestId('agent-pager'), 'momentumScrollEnd', {
          nativeEvent: { contentOffset: { x: PAGES.indexOf('workout') * 400 } },
        });
      expect(screen.getByText('detail:workout:true')).toBeTruthy();
      mockWidth = 800;
      result.rerender(wrap('sleep'));
      expect(screen.getByText('detail:workout:true')).toBeTruthy();
      expect(screen.getByText('detail:sleep:false')).toBeTruthy();
      expect(scroll).toHaveBeenLastCalledWith({
        offset: PAGES.indexOf('workout') * 800,
        animated: false,
      });
    } finally {
      mockWidth = 400;
      scroll.mockRestore();
    }
  },
);

test('kitchen is a page of the pager and renders the kitchen panel', () => {
  expect(PAGES[PAGES.length - 1]).toBe('kitchen');
  render(wrap('kitchen'));
  expect(screen.getByText('kitchen-panel')).toBeTruthy();
  expect(screen.getByText(/Kitchen/)).toBeTruthy();
});
