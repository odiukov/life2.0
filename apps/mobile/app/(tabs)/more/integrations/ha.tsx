import React from 'react';
import { Screen } from '@life-agents/ui';
import { HaPanel } from '@/features/integrations/panels/HaPanel';
import { useIntegrationsStore } from '@/features/integrations/store';

export default function HAScreen() {
  const setStatus = useIntegrationsStore((s) => s.set);
  return (
    <Screen>
      <HaPanel
        onConnected={() => setStatus('ha', 'connected')}
        onDisconnected={() => setStatus('ha', 'not-connected')}
      />
    </Screen>
  );
}
