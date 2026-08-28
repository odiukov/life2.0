import React from 'react';
import { act, render, screen } from '@testing-library/react-native';
import { StyleSheet } from 'react-native';
import { ThemeProvider } from '@life-agents/ui';
import { HomeScreen } from './HomeScreen';

// ── Sheet sub-components: stub out so their heavy deps don't interfere ────────
jest.mock('../more/SettingsSheet', () => ({ SettingsSheet: () => null }));
jest.mock('./AgentDetailSheet', () => ({ AgentDetailSheet: () => null }));
jest.mock('@/features/integrations/IntegrationSheet', () => ({
  IntegrationSheet: () => null,
}));

// ── Core data hooks ───────────────────────────────────────────────────────────
jest.mock('@/features/home/useHomeSummary', () => ({
  useHomeSummary: () => ({
    data: { agents: [], rings: null, briefingText: null, alerts: [] },
    isLoading: false,
    isError: false,
    isRefreshing: false,
    refetch: jest.fn(),
    onRefresh: jest.fn(),
  }),
}));

jest.mock('@/features/agents/useAgentStatusRows', () => ({
  useAgentStatusRows: () => ({
    rows: [
      {
        id: 'mood',
        status: 'needs_setup',
        hint: 'Log your first mood',
        cta: { kind: 'chat-prefill', tag: 'mood' },
      },
      {
        id: 'sleep',
        status: 'needs_setup',
        hint: 'Connect Apple Health',
        cta: { kind: 'integrations', panel: 'appleHealth' },
      },
      {
        id: 'recovery',
        status: 'ready',
        hint: '+4 vs avg',
        cta: null,
      },
    ],
    readyCount: 1,
    totalCount: 3,
    lastSyncedAt: null,
    isSyncing: false,
    isLoading: false,
  }),
}));

jest.mock('@/features/auth/useSession', () => ({
  useSession: () => ({ session: null }),
}));

jest.mock('@/features/agents/agentTileDispatch', () => ({
  dispatchTilePress: jest.fn(),
}));

jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn() }),
}));

function Wrapper({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}

type TestNode = {
  parent: TestNode | null;
  props: { onPress?: unknown; style?: unknown };
};

function findPressableAncestor(node: TestNode): TestNode {
  let current: TestNode | null = node;
  while (current) {
    if (typeof current.props.onPress === 'function' && typeof current.props.style === 'function') {
      return current;
    }
    current = current.parent;
  }
  throw new Error('Pressable ancestor not found');
}

function getUnpressedStyle(node: TestNode) {
  const style = node.props.style;
  return StyleSheet.flatten(typeof style === 'function' ? style({ pressed: false }) : style);
}

describe('AgentTile states', () => {
  it('renders log pill for chat-prefill (mood needs_setup)', () => {
    render(<HomeScreen />, { wrapper: Wrapper });
    expect(screen.getByText('log')).toBeTruthy();
  });

  it('renders connect pill for integrations (sleep needs_setup)', () => {
    render(<HomeScreen />, { wrapper: Wrapper });
    expect(screen.getByText('connect')).toBeTruthy();
  });

  it('renders hint text for needs_setup tile', () => {
    render(<HomeScreen />, { wrapper: Wrapper });
    expect(screen.getByText('Log your first mood')).toBeTruthy();
  });

  it('renders no pill for ready tile (recovery)', () => {
    render(<HomeScreen />, { wrapper: Wrapper });
    // ready tiles have no pill — only one 'connect' and one 'log' pill exist
    expect(screen.queryAllByText('log')).toHaveLength(1);
    expect(screen.queryAllByText('connect')).toHaveLength(1);
    expect(screen.queryAllByText('upload')).toHaveLength(0);
  });

  it('keeps tiles without hint text the same reserved height', () => {
    render(<HomeScreen />, { wrapper: Wrapper });

    const homeTile = findPressableAncestor(screen.getByText('Home'));
    const style = getUnpressedStyle(homeTile);

    expect(style.minHeight).toBe(76);
  });
});

describe('Home greeting', () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it('refreshes while the mounted Home screen crosses into morning', () => {
    jest.useFakeTimers();
    jest.setSystemTime(new Date(2026, 4, 5, 18, 30, 0));

    render(<HomeScreen />, { wrapper: Wrapper });
    expect(screen.getByText('Good evening, there')).toBeTruthy();

    act(() => {
      jest.setSystemTime(new Date(2026, 4, 6, 8, 0, 0));
      jest.advanceTimersByTime(60_000);
    });

    expect(screen.getByText('Good morning, there')).toBeTruthy();
  });
});
