import React from 'react';
import { StatusPill } from './index';

export default { title: 'today/StatusPill', component: StatusPill };

export const Success = () => <StatusPill tone="success">On track</StatusPill>;
export const Warn = () => <StatusPill tone="warn">Needs attention</StatusPill>;
export const Danger = () => <StatusPill tone="danger">Off track</StatusPill>;
export const Neu = () => <StatusPill tone="neu">No data</StatusPill>;
