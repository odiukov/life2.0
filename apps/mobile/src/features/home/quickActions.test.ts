import { QUICK_ACTIONS } from './quickActions';

test('each agent has exactly 3 quick actions', () => {
  const ids = ['sleep','workout','nutrition','mood','habits','medication','recovery','calendar','finance','home'] as const;
  ids.forEach(id => {
    expect(QUICK_ACTIONS[id]).toHaveLength(3);
    QUICK_ACTIONS[id].forEach(a => {
      expect(typeof a.label).toBe('string');
      expect(typeof a.subtitle).toBe('string');
      expect(typeof a.message).toBe('string');
      expect(a.message.startsWith('/')).toBe(true);
    });
  });
});
