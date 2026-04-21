import { useLocalSearchParams } from 'expo-router';
import { Screen, ScreenState } from '@life-agents/ui';

export default function AgentDetail() {
  const { agent } = useLocalSearchParams<{ agent: string }>();
  return <Screen><ScreenState kind="empty" title={`Agent: ${agent}`} body="Detail screen lands in P3-b." /></Screen>;
}
