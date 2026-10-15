import { openTask, useTaskSheet } from './sheetStore';

beforeEach(() => useTaskSheet.setState({ visible: false, origin: null, pending: null, queue: [] }));

test('a request is handed out exactly once', () => {
  openTask({ send: 'hi', origin: { x: 10, y: 20 } });
  const s = useTaskSheet.getState();
  expect(s.visible).toBe(true);
  expect(s.origin).toEqual({ x: 10, y: 20 });
  expect(s.take()).toEqual({ send: 'hi', origin: { x: 10, y: 20 } });
  expect(useTaskSheet.getState().take()).toBeNull();
});

test('a bare open keeps a request that is not taken yet and the last origin', () => {
  openTask({ lead: 'sleep', origin: { x: 1, y: 2 } });
  openTask();
  expect(useTaskSheet.getState().pending).toEqual({ lead: 'sleep', origin: { x: 1, y: 2 } });
  expect(useTaskSheet.getState().origin).toEqual({ x: 1, y: 2 });
});

test('hide drops what was not taken', () => {
  openTask({ prefill: 'x' });
  useTaskSheet.getState().hide();
  expect(useTaskSheet.getState()).toMatchObject({ visible: false, pending: null });
});

test('multiple requests remain FIFO through bare opens and hide clears the tail', () => {
  useTaskSheet.getState().hide();
  openTask({ send: 'first' });
  openTask({ send: 'second' });
  openTask();
  expect(useTaskSheet.getState().take()).toEqual({ send: 'first' });
  expect(useTaskSheet.getState().pending).toEqual({ send: 'second' });
  useTaskSheet.getState().hide();
  expect(useTaskSheet.getState().take()).toBeNull();
});
