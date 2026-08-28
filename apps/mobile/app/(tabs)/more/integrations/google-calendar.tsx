import React from 'react';
import { Screen } from '@life-agents/ui';
import { GoogleCalendarPanel } from '@/features/integrations/panels/GoogleCalendarPanel';
import { useIntegrationsStore } from '@/features/integrations/store';

export default function GoogleCalendarScreen() {
  const setStatus = useIntegrationsStore((s) => s.set);
  return (
    <Screen>
      <GoogleCalendarPanel
        onConnected={() => setStatus('calendar', 'connected')}
        onDisconnected={() => setStatus('calendar', 'not-connected')}
      />
    </Screen>
  );
}
