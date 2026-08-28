import { create } from 'zustand';
import type { Session } from '@supabase/supabase-js';
import { SUPABASE_CONFIGURED, supabase } from './SupabaseClient';

type State = {
  session: Session | null;
  ready: boolean;
  signOut: () => Promise<void>;
};

export const useSession = create<State>((set) => {
  if (SUPABASE_CONFIGURED) {
    supabase.auth
      .getSession()
      .then(({ data }) => set({ session: data.session, ready: true }))
      .catch(() => set({ ready: true }));
    supabase.auth.onAuthStateChange((_e, s) => set({ session: s }));
  } else {
    // Supabase env missing → pretend we're ready with no session so the
    // app boots to /(auth)/sign-in and renders a helpful message.
    setTimeout(() => set({ ready: true }), 0);
  }
  return {
    session: null,
    ready: false,
    signOut: async () => {
      if (SUPABASE_CONFIGURED) await supabase.auth.signOut();
    },
  };
});
