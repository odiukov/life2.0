import React from 'react';
import { Screen } from '@life-agents/ui';
import { YazioPanel } from '@/features/integrations/panels/YazioPanel';
import { useIntegrationsStore } from '@/features/integrations/store';

export default function YazioScreen() {
  const setStatus = useIntegrationsStore((s) => s.set);
  return (
    <Screen>
      <YazioPanel
        onConnected={() => setStatus('yazio', 'connected')}
        onDisconnected={() => setStatus('yazio', 'not-connected')}
      />
    </Screen>
  );
}
