import React from 'react';
import { Bubble } from './index';

export default { title: 'chat/Bubble', component: Bubble };

export const Assistant = () => <Bubble variant="assistant">Assistant message</Bubble>;
export const User = () => <Bubble variant="user">User message</Bubble>;
export const Log = () => <Bubble variant="log">Log entry</Bubble>;
export const Alert = () => <Bubble variant="alert" accentTone="warn">Alert with warn tone</Bubble>;
