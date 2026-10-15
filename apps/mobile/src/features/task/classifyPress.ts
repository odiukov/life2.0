export const HOLD_MS = 350;
export const CANCEL_DX = -80;

export type PressOutcome = 'tap' | 'send' | 'cancel';

/** What a released press means. `held` = the gesture handler activated the hold (≥ HOLD_MS). */
export function classifyPress({ held, dx }: { held: boolean; dx: number }): PressOutcome {
  if (!held) return 'tap';
  return isCancelArmed(dx) ? 'cancel' : 'send';
}

export function isCancelArmed(dx: number): boolean {
  return dx < CANCEL_DX;
}
