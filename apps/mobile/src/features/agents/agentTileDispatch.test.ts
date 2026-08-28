import { dispatchTilePress } from './agentTileDispatch';
import type { AgentRow } from './agentStatusRules';

function makeRow(over: Partial<AgentRow>): AgentRow {
  return {
    id: 'mood',
    description: 'Daily mood, energy, sentiment',
    status: 'ready',
    hint: null,
    cta: null,
    ...over,
  };
}

const ctx = () => ({
  router: { push: jest.fn() },
  openIntegration: jest.fn(),
  openDetail: jest.fn(),
});

describe('dispatchTilePress', () => {
  it('opens AgentDetailSheet when cta is null', () => {
    const c = ctx();
    dispatchTilePress(makeRow({ cta: null }), c);
    expect(c.openDetail).toHaveBeenCalledWith('mood');
    expect(c.openIntegration).not.toHaveBeenCalled();
    expect(c.router.push).not.toHaveBeenCalled();
  });

  it('opens IntegrationSheet for kind=integrations with panel', () => {
    const c = ctx();
    dispatchTilePress(
      makeRow({
        id: 'sleep',
        cta: { kind: 'integrations', panel: 'apple-health' },
        status: 'needs_setup',
      }),
      c,
    );
    expect(c.openIntegration).toHaveBeenCalledWith('apple-health');
    expect(c.openDetail).not.toHaveBeenCalled();
    expect(c.router.push).not.toHaveBeenCalled();
  });

  it('navigates to /(tabs)/chat with prefill+tag for kind=chat-prefill', () => {
    const c = ctx();
    dispatchTilePress(
      makeRow({
        id: 'mood',
        cta: { kind: 'chat-prefill', text: '', tag: 'mood' },
        status: 'needs_setup',
      }),
      c,
    );
    expect(c.router.push).toHaveBeenCalledWith({
      pathname: '/(tabs)/chat',
      params: { prefill: '', tag: 'mood' },
    });
    expect(c.openDetail).not.toHaveBeenCalled();
    expect(c.openIntegration).not.toHaveBeenCalled();
  });

  it('navigates to /(tabs)/more/integrations for kind=finance-upload', () => {
    const c = ctx();
    dispatchTilePress(
      makeRow({
        id: 'finance',
        cta: { kind: 'finance-upload' },
        status: 'needs_setup',
      }),
      c,
    );
    expect(c.router.push).toHaveBeenCalledWith('/(tabs)/more/integrations');
    expect(c.openDetail).not.toHaveBeenCalled();
    expect(c.openIntegration).not.toHaveBeenCalled();
  });

  it('opens IntegrationSheet branch is a no-op when panel is missing', () => {
    const c = ctx();
    dispatchTilePress(
      makeRow({
        id: 'home',
        cta: { kind: 'integrations' },
        status: 'needs_setup',
      }),
      c,
    );
    expect(c.openIntegration).not.toHaveBeenCalled();
    expect(c.openDetail).not.toHaveBeenCalled();
    expect(c.router.push).not.toHaveBeenCalled();
  });

  it('navigates to chat without tag key when cta.tag is undefined', () => {
    const c = ctx();
    dispatchTilePress(
      makeRow({
        id: 'mood',
        cta: { kind: 'chat-prefill', text: '' },
        status: 'needs_setup',
      }),
      c,
    );
    expect(c.router.push).toHaveBeenCalledWith({
      pathname: '/(tabs)/chat',
      params: { prefill: '' },
    });
    expect(c.openDetail).not.toHaveBeenCalled();
    expect(c.openIntegration).not.toHaveBeenCalled();
  });
});
