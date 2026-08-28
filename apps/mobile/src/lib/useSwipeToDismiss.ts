import { Dimensions } from 'react-native';
import { Gesture, type PanGesture } from 'react-native-gesture-handler';
import {
  Easing,
  runOnJS,
  useAnimatedScrollHandler,
  useSharedValue,
  withSpring,
  withTiming,
  type SharedValue,
} from 'react-native-reanimated';
import { BACKDROP_OUT_MS, EXIT_MS, SHEET_SPRING } from './sheetAnimation';

// ─── Module-level constants ───────────────────────────────────────────────────

export const DISMISS_DISTANCE_PX = 120;
export const DISMISS_VELOCITY_PX_S = 800;

const { height: SCREEN_HEIGHT } = Dimensions.get('window');

const ENTRY_LOCKOUT_MS = 300; // ignore gesture during entry animation
const VERTICAL_ACTIVATION_PX = 10; // start tracking after this much downward motion
const HORIZONTAL_FAIL_PX = 15; // give horizontal pans (charts) priority

// ─── Types ────────────────────────────────────────────────────────────────────

export type DismissInputs = {
  translationY: number;
  velocityY: number;
};

export type UseSwipeToDismissOptions = {
  sheetY: SharedValue<number>;
  backdropAlpha: SharedValue<number>;
  onClose: () => void;
  /**
   * Called on the JS thread the moment the exit animation starts.
   * Use to unwind synchronous side animations in the parent
   * (e.g. ProfileSheet card-stack scale) so they finish in step with the sheet.
   */
  onCloseStart?: () => void;
  /**
   * If true, the gesture is always active regardless of inner scroll position.
   * Set this for sheets without a scrollable child, or when sub-panel content
   * is short enough that scroll coordination is unnecessary.
   * Default: false (gesture defers to scroll when scroll is not at top).
   */
  ignoreScroll?: boolean;
  /** When false, the gesture is disabled. Default: true. */
  enabled?: boolean;
};

export type UseSwipeToDismissResult = {
  panGesture: PanGesture;
  scrollHandler: ReturnType<typeof useAnimatedScrollHandler>;
};

// ─── Pure helpers ────────────────────────────────────────────────────────────

/**
 * Decide whether a release of the drag should close the sheet.
 * Closes if the user dragged more than DISMISS_DISTANCE_PX downward,
 * or if the release velocity is faster than DISMISS_VELOCITY_PX_S downward.
 * Upward drags / velocities never close.
 */
export function shouldDismiss({ translationY, velocityY }: DismissInputs): boolean {
  if (translationY > DISMISS_DISTANCE_PX) return true;
  if (translationY > 0 && velocityY > DISMISS_VELOCITY_PX_S) return true;
  return false;
}

export type ScrollSyncState = {
  translationOffsetY: number;
  inScrollMode: boolean;
};

export const INITIAL_SCROLL_SYNC_STATE: ScrollSyncState = {
  translationOffsetY: 0,
  inScrollMode: false,
};

/**
 * Reconcile pan translation with inner scroll position so that translation
 * accumulated while the inner ScrollView was consuming the swipe doesn't yank
 * the sheet down once scroll reaches the top.
 *
 * - While `scrollY > 0`: the inner scroll owns the gesture. We track the latest
 *   translation as `translationOffsetY` so that on the first frame at
 *   scroll-top, `effective = translationY - offset = 0` (no jump).
 * - First frame at scroll-top after scrolling: freeze the offset and start
 *   reporting `effective` relative to that point.
 * - After that: `effective = translationY - frozenOffset` flows naturally as
 *   the user keeps pulling, so a continuous swipe still drives pull-to-dismiss.
 */
export function nextScrollSyncState(
  translationY: number,
  scrollY: number,
  ignoreScroll: boolean,
  prev: ScrollSyncState,
): { state: ScrollSyncState; effectiveTranslationY: number } {
  'worklet';
  if (!ignoreScroll && scrollY > 0) {
    return {
      state: { translationOffsetY: translationY, inScrollMode: true },
      effectiveTranslationY: 0,
    };
  }
  if (!ignoreScroll && prev.inScrollMode) {
    return {
      state: { translationOffsetY: translationY, inScrollMode: false },
      effectiveTranslationY: 0,
    };
  }
  return {
    state: prev,
    effectiveTranslationY: translationY - prev.translationOffsetY,
  };
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

export function useSwipeToDismiss(opts: UseSwipeToDismissOptions): UseSwipeToDismissResult {
  const {
    sheetY,
    backdropAlpha,
    onClose,
    onCloseStart,
    ignoreScroll = false,
    enabled = true,
  } = opts;

  const scrollY = useSharedValue(0);
  const mountedAt = useSharedValue(Date.now());
  const translationOffsetY = useSharedValue(0);
  const inScrollMode = useSharedValue(false);

  const scrollHandler = useAnimatedScrollHandler({
    onScroll: (e) => {
      scrollY.value = e.contentOffset.y;
    },
  });

  function dismiss() {
    'worklet';
    if (onCloseStart) runOnJS(onCloseStart)();
    backdropAlpha.value = withTiming(0, {
      duration: BACKDROP_OUT_MS,
      easing: Easing.in(Easing.quad),
    });
    sheetY.value = withTiming(
      SCREEN_HEIGHT,
      { duration: EXIT_MS, easing: Easing.in(Easing.cubic) },
      (finished) => {
        if (finished) runOnJS(onClose)();
      },
    );
  }

  function springBack() {
    'worklet';
    sheetY.value = withSpring(0, SHEET_SPRING);
    backdropAlpha.value = withTiming(1, {
      duration: BACKDROP_OUT_MS,
      easing: Easing.out(Easing.quad),
    });
  }

  const panGesture = Gesture.Pan()
    .enabled(enabled)
    .activeOffsetY([VERTICAL_ACTIVATION_PX, 999])
    .failOffsetX([-HORIZONTAL_FAIL_PX, HORIZONTAL_FAIL_PX])
    // onBegin is a notification in RNGH 2.x — returning early does NOT block
    // onUpdate/onEnd, so entry-lockout is enforced there instead.
    .onBegin(() => {
      'worklet';
      translationOffsetY.value = 0;
      inScrollMode.value = false;
    })
    .onUpdate((e) => {
      'worklet';
      if (Date.now() - mountedAt.value < ENTRY_LOCKOUT_MS) return;
      const next = nextScrollSyncState(e.translationY, scrollY.value, ignoreScroll, {
        translationOffsetY: translationOffsetY.value,
        inScrollMode: inScrollMode.value,
      });
      translationOffsetY.value = next.state.translationOffsetY;
      inScrollMode.value = next.state.inScrollMode;
      const ty = Math.max(0, next.effectiveTranslationY);
      sheetY.value = ty;
      backdropAlpha.value = Math.max(0, Math.min(1, 1 - ty / SCREEN_HEIGHT));
    })
    .onEnd((e) => {
      'worklet';
      if (Date.now() - mountedAt.value < ENTRY_LOCKOUT_MS) {
        springBack();
        return;
      }
      const effective = e.translationY - translationOffsetY.value;
      const close =
        effective > DISMISS_DISTANCE_PX || (effective > 0 && e.velocityY > DISMISS_VELOCITY_PX_S);
      if (close) dismiss();
      else springBack();
    })
    .onFinalize((_e, success) => {
      'worklet';
      if (!success) springBack();
    });

  return { panGesture, scrollHandler };
}
