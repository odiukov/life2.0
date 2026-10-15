import { useQuery } from '@tanstack/react-query';
import type { GatewaySchemas } from '@life-agents/api-client';
import { gateway } from '@/api/gateway';

export type FeedItem = GatewaySchemas['FeedItemOut'];
export type DayFeedData = GatewaySchemas['FeedOut'];
export const FEED_KEY = ['me-feed'] as const;
export const MAX_OFFSET = 30;

const pad = (n: number) => String(n).padStart(2, '0');

/** The local calendar date `offset` days before `today` (the device's day; the server checks the range). */
export function feedDay(today: Date, offset: number): string {
  const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - offset);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function useDayFeed(day: string) {
  return useQuery({
    queryKey: [...FEED_KEY, day],
    queryFn: async (): Promise<DayFeedData> => {
      const { data, error } = await gateway.GET('/me/feed', { params: { query: { date: day } } });
      if (error) throw error;
      return data as DayFeedData;
    },
  });
}
