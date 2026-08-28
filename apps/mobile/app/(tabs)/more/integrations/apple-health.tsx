import React from 'react';
import { Screen } from '@life-agents/ui';
import { AppleHealthPanel } from '@/features/integrations/panels/AppleHealthPanel';
import { useIntegrationsStore } from '@/features/integrations/store';

export default function AppleHealthScreen() {
  const setStatus = useIntegrationsStore((s) => s.set);
  return (
    <Screen>
      <AppleHealthPanel
        onConnected={() => setStatus('apple-health', 'connected')}
        onDisconnected={() => setStatus('apple-health', 'not-connected')}
      />
    </Screen>
  );
}
