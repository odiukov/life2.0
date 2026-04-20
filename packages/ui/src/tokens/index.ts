export * from './colors';
export * from './typography';
export * from './spacing';
export * from './radius';

import { colors } from './colors';
import { typography } from './typography';
import { spacing } from './spacing';
import { radius } from './radius';

export const tokens = { colors, typography, spacing, radius } as const;
