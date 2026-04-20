import React from 'react';
import { AskBar } from './index';

export default { title: 'chat/AskBar', component: AskBar };

export const Basic = () => (
  <AskBar
    onSubmit={() => undefined}
    onVoice={() => undefined}
    onAction={() => undefined}
  />
);
