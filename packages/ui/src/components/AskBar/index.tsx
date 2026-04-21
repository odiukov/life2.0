import React, { useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';
import { useTheme } from '../../theme';
import { Icon } from '../Icon';

export function AskBar({
  value: controlledValue,
  onChangeText,
  onSubmit,
  onVoice,
  onAction,
}: {
  value?: string;
  onChangeText?: (text: string) => void;
  onSubmit: (text: string) => void;
  onVoice?: () => void;
  onAction?: () => void;
}) {
  const { colors, radius, spacing, typography } = useTheme();
  const [internalValue, setInternalValue] = useState('');
  const isControlled = controlledValue !== undefined && onChangeText !== undefined;
  const value = isControlled ? controlledValue : internalValue;
  const setValue = isControlled ? onChangeText! : setInternalValue;

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
        <Icon name="Microphone" size={20} color={colors.accentHi} testID="ask-mic-icon" />
      </Pressable>
      <Pressable testID="ask-action" onPress={onAction} hitSlop={8} style={{ marginLeft: spacing.s2 }}>
        <Icon name="Plus" size={20} color={colors.accentHi} testID="ask-plus-icon" />
      </Pressable>
      <Pressable testID="ask-send" onPress={send} hitSlop={8} style={{ marginLeft: spacing.s2 }}>
        <Icon name="PaperPlaneRight" size={20} color={value.trim() ? colors.accentHi : colors.fg3} testID="ask-send-icon" weight="fill" />
      </Pressable>
    </View>
  );
}


const styles = StyleSheet.create({
  bar: { borderWidth: 1, flexDirection: 'row', alignItems: 'flex-end' },
});
