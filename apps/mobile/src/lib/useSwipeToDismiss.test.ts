import { INITIAL_SCROLL_SYNC_STATE, nextScrollSyncState, shouldDismiss } from './useSwipeToDismiss';

describe('shouldDismiss', () => {
  test('returns false for tiny drag', () => {
    expect(shouldDismiss({ translationY: 20, velocityY: 0 })).toBe(false);
  });

  test('returns false at exactly the distance threshold', () => {
    expect(shouldDismiss({ translationY: 120, velocityY: 0 })).toBe(false);
  });

  test('returns true just over the distance threshold', () => {
    expect(shouldDismiss({ translationY: 121, velocityY: 0 })).toBe(true);
  });

  test('returns true on high velocity even with small translation', () => {
    expect(shouldDismiss({ translationY: 30, velocityY: 1500 })).toBe(true);
  });

  test('returns false at exactly the velocity threshold', () => {
    expect(shouldDismiss({ translationY: 30, velocityY: 800 })).toBe(false);
  });

  test('returns true just over the velocity threshold', () => {
    expect(shouldDismiss({ translationY: 30, velocityY: 801 })).toBe(true);
  });

  test('returns false for upward drag (negative translation)', () => {
    expect(shouldDismiss({ translationY: -200, velocityY: -2000 })).toBe(false);
  });

  test('returns false for upward velocity (negative)', () => {
    expect(shouldDismiss({ translationY: 50, velocityY: -1500 })).toBe(false);
  });
});

describe('nextScrollSyncState', () => {
  test('gesture starts at scroll-top: effective tracks raw translation', () => {
    const r = nextScrollSyncState(40, 0, false, INITIAL_SCROLL_SYNC_STATE);
    expect(r.effectiveTranslationY).toBe(40);
    expect(r.state).toEqual(INITIAL_SCROLL_SYNC_STATE);
  });

  test('while inner scroll is non-zero: sheet stays put, offset tracks translation', () => {
    const r = nextScrollSyncState(80, 200, false, INITIAL_SCROLL_SYNC_STATE);
    expect(r.effectiveTranslationY).toBe(0);
    expect(r.state).toEqual({ translationOffsetY: 80, inScrollMode: true });
  });

  test('continued scroll keeps offset matched so effective stays at 0', () => {
    const prev = { translationOffsetY: 80, inScrollMode: true };
    const r = nextScrollSyncState(160, 50, false, prev);
    expect(r.effectiveTranslationY).toBe(0);
    expect(r.state).toEqual({ translationOffsetY: 160, inScrollMode: true });
  });

  test('first frame at scroll-top after scrolling: offset freezes at current ty, effective is 0 (no jump)', () => {
    const prev = { translationOffsetY: 250, inScrollMode: true };
    const r = nextScrollSyncState(300, 0, false, prev);
    expect(r.effectiveTranslationY).toBe(0);
    expect(r.state).toEqual({ translationOffsetY: 300, inScrollMode: false });
  });

  test('after offset is frozen, continued pull grows effective from 0', () => {
    const prev = { translationOffsetY: 300, inScrollMode: false };
    const r = nextScrollSyncState(350, 0, false, prev);
    expect(r.effectiveTranslationY).toBe(50);
    expect(r.state).toEqual(prev);
  });

  test('ignoreScroll: scroll position is irrelevant, effective tracks raw translation', () => {
    const r = nextScrollSyncState(60, 200, true, INITIAL_SCROLL_SYNC_STATE);
    expect(r.effectiveTranslationY).toBe(60);
    expect(r.state).toEqual(INITIAL_SCROLL_SYNC_STATE);
  });

  test('end-to-end: scroll back to top then keep pulling, effective grows past dismiss threshold', () => {
    let state = INITIAL_SCROLL_SYNC_STATE;
    // user is mid-scroll, pulls down to scroll back up
    ({ state } = nextScrollSyncState(100, 200, false, state));
    ({ state } = nextScrollSyncState(200, 100, false, state));
    // scroll just hit top with cumulative translation of 250
    let r = nextScrollSyncState(250, 0, false, state);
    expect(r.effectiveTranslationY).toBe(0); // no jump
    state = r.state;
    // user keeps pulling another 130px
    r = nextScrollSyncState(380, 0, false, state);
    expect(r.effectiveTranslationY).toBe(130);
    expect(shouldDismiss({ translationY: r.effectiveTranslationY, velocityY: 0 })).toBe(true);
  });

  test('end-to-end: scroll back to top and release immediately, effective near 0 (no false dismiss)', () => {
    let state = INITIAL_SCROLL_SYNC_STATE;
    ({ state } = nextScrollSyncState(150, 200, false, state));
    ({ state } = nextScrollSyncState(300, 50, false, state));
    const r = nextScrollSyncState(320, 0, false, state);
    expect(r.effectiveTranslationY).toBe(0);
    expect(shouldDismiss({ translationY: r.effectiveTranslationY, velocityY: 0 })).toBe(false);
  });
});
