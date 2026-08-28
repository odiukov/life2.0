import React from 'react';
import { ScreenState } from './index';

export default { title: 'primitives/ScreenState', component: ScreenState };

export const Loading = () => <ScreenState kind="loading" skeletonCount={3} />;

export const Empty = () => (
  <ScreenState
    kind="empty"
    title="Nothing here yet"
    body="Start by adding your first entry."
    cta={{ label: 'Get started', onPress: () => undefined }}
  />
);

export const Error = () => (
  <ScreenState
    kind="error"
    title="Something went wrong"
    body="We could not load your data."
    cta={{ label: 'Try again', onPress: () => undefined }}
  />
);
