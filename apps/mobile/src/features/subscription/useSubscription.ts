export type PackId = 'spark' | 'flow' | 'deep';

export type SubscriptionState = {
  balance: { used: number; total: number; renewsOn: string; weekUsed: number };
  plan: { active: boolean; renewsOn: string };
  purchase: (packId: PackId) => Promise<void>;
  startPlan: () => Promise<void>;
  managePlan: () => void;
  restore: () => Promise<void>;
  loading: boolean;
};

export function useSubscription(): SubscriptionState {
  return {
    balance: { used: 1340, total: 2500, renewsOn: 'May 14', weekUsed: 412 },
    plan: { active: true, renewsOn: 'May 14' },
    purchase: async (_packId) => { console.log('TODO: wire IAP purchase', _packId); },
    startPlan: async () => { console.log('TODO: wire IAP startPlan'); },
    managePlan: () => { console.log('TODO: wire IAP managePlan'); },
    restore: async () => { console.log('TODO: wire IAP restore'); },
    loading: false,
  };
}
