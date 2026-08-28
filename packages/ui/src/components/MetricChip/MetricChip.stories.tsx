import React from 'react';
import { MetricChip } from './index';

export default { title: 'primitives/MetricChip', component: MetricChip };

export const Up = () => <MetricChip variant="up">+8%</MetricChip>;
export const Down = () => <MetricChip variant="down">-3</MetricChip>;
export const Neu = () => <MetricChip variant="neu">7h12m</MetricChip>;
