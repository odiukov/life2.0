import { create } from 'zustand';
import type { Session } from '@supabase/supabase-js';
import { SUPABASE_CONFIGURED, supabase } from './SupabaseClient';
import { DEV_USER_ID } from './getAuthHeaders';

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
  } else if (DEV_USER_ID) {
    // Supabase env missing but a dev user is pinned → synthesise a session so
    // the app boots straight into the tabs against `AUTH_MODE=dev` backend.
    const devSession = {
      user: { id: DEV_USER_ID, user_metadata: { full_name: 'Demo' } },
    } as unknown as Session;
    setTimeout(() => set({ session: devSession, ready: true }), 0);
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
