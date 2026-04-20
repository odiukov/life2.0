import React from 'react';
import { AlertCard } from './index';

export default { title: 'today/AlertCard', component: AlertCard };

export const Info = () => (
  <AlertCard
    title="Reminder"
    body="Your morning check-in is due."
    tone="info"
    timestamp="09:00"
  />
);

export const Warn = () => (
  <AlertCard
    title="Low sleep"
    body="You averaged under 6 hours this week."
    tone="warn"
    timestamp="Yesterday"
  />
);

export const Danger = () => (
  <AlertCard
    title="Missed medication"
    body="You did not log your evening medication."
    tone="danger"
    timestamp="2 hours ago"
  />
);
