import React, { useEffect } from 'react';

export function useRouter() {
  return { push: jest.fn(), replace: jest.fn(), back: jest.fn() };
}

export function useLocalSearchParams<T extends Record<string, string>>(): Partial<T> {
  return {};
}

export function Link({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function useFocusEffect(effect: () => void) {
  const stable = React.useRef(effect);
  stable.current = effect;
  useEffect(() => stable.current(), []);
}
