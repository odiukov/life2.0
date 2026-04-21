import { render, screen, waitFor } from '@testing-library/react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { ThemeProvider } from '@life-agents/ui';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TodayScreen } from './TodayScreen';

// Use a plain QueryClientProvider to avoid PersistQueryClientProvider's
// async restore phase which pauses all queries until MMKV hydration completes.
function QueryProvider({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

test('renders greeting and at least one alert', async () => {
  render(
    <QueryProvider>
      <SafeAreaProvider>
        <ThemeProvider>
          <TodayScreen />
        </ThemeProvider>
      </SafeAreaProvider>
    </QueryProvider>,
  );
  await waitFor(() => expect(screen.getByText('Good morning')).toBeOnTheScreen());
  await waitFor(() => expect(screen.getByText('Missed B12 for 2d')).toBeOnTheScreen());
});
