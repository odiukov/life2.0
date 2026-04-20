import React, { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';
import { useTheme } from '../../theme';

export function AskBar({
  onSubmit,
  onVoice,
  onAction,
}: {
  onSubmit: (text: string) => void;
  onVoice?: () => void;
  onAction?: () => void;
}) {
  const { colors, radius, spacing, typography } = useTheme();
  const [value, setValue] = useState('');
  const send = () => {
    if (!value.trim()) return;
    onSubmit(value.trim());
    setValue('');
  };
  return (
    <View
      style={[
        styles.bar,
        {
          backgroundColor: colors.bg2,
          borderColor: colors.border,
          borderRadius: radius.rXl,
          paddingHorizontal: spacing.s3,
          paddingVertical: spacing.s2,
          marginHorizontal: spacing.s3,
          marginVertical: spacing.s2,
        },
      ]}
    >
      <TextInput
        style={[typography.body, { color: colors.fg1, flex: 1 }]}
        placeholder="Ask or log…"
        placeholderTextColor={colors.fg3}
        value={value}
        onChangeText={setValue}
        multiline
        blurOnSubmit={false}
      />
      <Pressable testID="ask-mic" onPress={onVoice} hitSlop={8}>
        <MicGlyph color={colors.accentHi} />
      </Pressable>
      <Pressable testID="ask-action" onPress={onAction} hitSlop={8} style={{ marginLeft: spacing.s2 }}>
        <PlusGlyph color={colors.accentHi} />
      </Pressable>
      <Pressable testID="ask-send" onPress={send} hitSlop={8} style={{ marginLeft: spacing.s2 }}>
        <SendGlyph color={value.trim() ? colors.accentHi : colors.fg3} />
      </Pressable>
    </View>
  );
}

function MicGlyph({ color }: { color: string }) {
  return <View style={{ width: 20, height: 20 }}>{/* replaced by phosphor icon in Task 8 */}</View>;
}
function PlusGlyph({ color }: { color: string }) {
  return <View style={{ width: 20, height: 20 }}>{/* replaced by phosphor icon in Task 8 */}</View>;
}
function SendGlyph({ color }: { color: string }) {
  return <View style={{ width: 20, height: 20 }}>{/* replaced by phosphor icon in Task 8 */}</View>;
}

const styles = StyleSheet.create({
  bar: { borderWidth: 1, flexDirection: 'row', alignItems: 'flex-end' },
});
