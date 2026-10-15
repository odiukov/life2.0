import * as Haptics from 'expo-haptics';

export type HapticKind = 'light' | 'medium' | 'success' | 'warning';

/** Best-effort feedback: simulators, low-power mode and old devices may refuse. */
export function haptic(kind: HapticKind): void {
  const run =
    kind === 'light'
      ? Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
      : kind === 'medium'
        ? Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)
        : Haptics.notificationAsync(
            kind === 'success'
              ? Haptics.NotificationFeedbackType.Success
              : Haptics.NotificationFeedbackType.Warning,
          );
  void run.catch(() => undefined);
}
