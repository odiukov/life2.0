import { render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider } from '@life-agents/ui';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DashScreen } from './DashScreen';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <SafeAreaProvider>
          <ThemeProvider>{children}</ThemeProvider>
        </SafeAreaProvider>
      </QueryClientProvider>
    );
  }
  return Wrapper;
}

test('renders 8 agent cards from mock dashboard', async () => {
  const Wrapper = makeWrapper();
  render(<DashScreen />, { wrapper: Wrapper });
  await waitFor(() => {
    expect(screen.getAllByTestId(/^agent-card-/)).toHaveLength(8);
  }, { timeout: 3000 });
});
