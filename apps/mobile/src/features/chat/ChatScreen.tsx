import React, { useEffect, useState } from 'react';
import { Text } from 'react-native';
import { Screen } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { useBottomTabBarHeight } from '@react-navigation/bottom-tabs';
import { appLocale } from '@/lib/locale';
import { TaskConversation } from '../task/TaskConversation';
import { useTask } from './useTask';

export function ChatScreen() {
  const chat = useTask();
  const keyboardOffset = useBottomTabBarHeight();
  const t = useT(appLocale());
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    void chat.restore().catch(() => setFailed(true));
  }, [chat.restore]);
  return (
    <Screen edges={['top']}>
      {failed && <Text>{t('chat.client.network')}</Text>}
      <TaskConversation chat={chat} keyboardOffset={keyboardOffset} />
    </Screen>
  );
}
