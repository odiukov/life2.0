import React from 'react';
import { Screen } from '@life-agents/ui';
import { GarminPanel } from '@/features/integrations/panels/GarminPanel';
import { useIntegrationsStore } from '@/features/integrations/store';

export default function GarminScreen() {
  const setStatus = useIntegrationsStore((s) => s.set);
  return (
    <Screen>
      <GarminPanel
        onConnected={() => setStatus('garmin', 'connected')}
        onDisconnected={() => setStatus('garmin', 'not-connected')}
      />
    </Screen>
  );
}
