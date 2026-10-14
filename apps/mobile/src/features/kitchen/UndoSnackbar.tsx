import React, { useEffect } from 'react';
import { Pressable, Text, View } from 'react-native';
import { useTheme } from '@life-agents/ui';

type Props = {
  visible: boolean;
  label: string;
  undoLabel: string;
  actionId?: string;
  onUndo: () => void;
  onHide: () => void;
  durationMs?: number;
};

export function UndoSnackbar({ visible, label, undoLabel, actionId, onUndo, onHide, durationMs = 5000 }: Props) {
  const { colors, spacing } = useTheme();
  useEffect(() => {
    if (!visible) return;
    const timer = setTimeout(onHide, durationMs);
    return () => clearTimeout(timer);
  }, [visible, label, actionId, durationMs, onHide]);
  if (!visible) return null;
  return (
    <View style={{ position: 'absolute', left: spacing.s4, right: spacing.s4, bottom: spacing.s4, backgroundColor: colors.bg3, borderRadius: 12, padding: spacing.s3, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
      <Text style={{ color: colors.fg1, flex: 1 }}>{label}</Text>
      <Pressable onPress={onUndo} hitSlop={8} accessibilityRole="button" accessibilityLabel={undoLabel}><Text style={{ color: colors.accentHi, fontWeight: '600' }}>{undoLabel}</Text></Pressable>
    </View>
  );
}
