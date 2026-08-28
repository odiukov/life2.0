import { useLocalSearchParams } from 'expo-router';
import { AgentDetailScreen } from '@/features/home/AgentDetailScreen';
import type { AgentId } from '@life-agents/ui';

export default function AgentDetailRoute() {
  const { agent } = useLocalSearchParams<{ agent: string }>();
  return <AgentDetailScreen agentId={(agent as AgentId) ?? 'sleep'} />;
}
