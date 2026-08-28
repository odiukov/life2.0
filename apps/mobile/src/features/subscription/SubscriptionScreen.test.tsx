import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react-native';
import { ThemeProvider } from '@life-agents/ui';
import { SubscriptionContent, SubscriptionScreen } from './SubscriptionScreen';

jest.mock('./useSubscription', () => ({
  useSubscription: () => ({
    balance: { used: 1340, total: 2500, renewsOn: 'May 14', weekUsed: 412 },
    plan: { active: true, renewsOn: 'May 14' },
    purchase: jest.fn().mockResolvedValue(undefined),
    startPlan: jest.fn().mockResolvedValue(undefined),
    managePlan: jest.fn(),
    restore: jest.fn().mockResolvedValue(undefined),
    loading: false,
  }),
}));

// react-native-svg and expo-router are auto-mocked via jest.config.ts moduleNameMapper
// AgentMark uses SVG icons — the svg mock renders them as Views

function Wrapper({ children }: { children: React.ReactNode }) {
  return <ThemeProvider>{children}</ThemeProvider>;
}

describe('SubscriptionScreen', () => {
  it('renders without crashing', () => {
    render(<SubscriptionScreen />, { wrapper: Wrapper });
  });

  it('shows the screen title', () => {
    render(<SubscriptionScreen />, { wrapper: Wrapper });
    expect(screen.getByText('Tokens & subscription')).toBeTruthy();
  });

  it('renders all three token pack names', () => {
    render(<SubscriptionScreen />, { wrapper: Wrapper });
    expect(screen.getByText('Spark')).toBeTruthy();
    expect(screen.getByText('Flow')).toBeTruthy();
    expect(screen.getByText('Deep')).toBeTruthy();
  });

  it('shows LIFE+ badge and Active status when plan is active', () => {
    render(<SubscriptionScreen />, { wrapper: Wrapper });
    expect(screen.getByText('LIFE+')).toBeTruthy();
    expect(screen.getByText('Active')).toBeTruthy();
  });

  it('shows all 6 token usage action labels', () => {
    render(<SubscriptionScreen />, { wrapper: Wrapper });
    expect(screen.getByText('Sleep analysis')).toBeTruthy();
    expect(screen.getByText("Plan today's session")).toBeTruthy();
    expect(screen.getByText('Readiness deep-dive')).toBeTruthy();
    expect(screen.getByText('Log meal & macros')).toBeTruthy();
    expect(screen.getByText('Quick journal reflection')).toBeTruthy();
    expect(screen.getByText('Spending summary')).toBeTruthy();
  });

  it('shows $6.99 price for Life+ plan', () => {
    render(<SubscriptionScreen />, { wrapper: Wrapper });
    expect(screen.getByText('$6.99')).toBeTruthy();
  });

  it('forwards scroll events for sheet swipe coordination', () => {
    const onScroll = jest.fn();
    render(<SubscriptionContent onScroll={onScroll} />, { wrapper: Wrapper });

    fireEvent.scroll(screen.getByTestId('subscription-scroll'), {
      nativeEvent: { contentOffset: { y: 64 } },
    });

    expect(onScroll).toHaveBeenCalled();
  });
});
