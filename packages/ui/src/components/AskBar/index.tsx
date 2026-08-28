import React, { forwardRef, useCallback, useImperativeHandle, useRef, useState } from 'react';
import { Pressable, StyleSheet, TextInput, View } from 'react-native';
import { useTheme } from '../../theme';
import { Icon } from '../Icon';
import { AgentChip } from '../AgentChip';
import type { AgentId } from '../AgentBadge';

const AGENT_NAMES: readonly AgentId[] = [
  'sleep',
  'workout',
  'nutrition',
  'mood',
  'habits',
  'recovery',
  'medication',
  'finance',
  'calendar',
  'home',
  'body',
];

const LEADING_TAG_RE = new RegExp(`^/(${AGENT_NAMES.join('|')})\\s(.*)$`, 's');

export type AskBarChange = { tag: AgentId | undefined; text: string };

export type AskBarHandle = { focus: () => void };

type AskBarProps = {
  value?: string;
  tag?: AgentId;
  onChangeText?: (next: AskBarChange) => void;
  onSubmit: (next: AskBarChange) => void;
  onVoice?: () => void;
  onAttach?: () => void;
  hasAttachment?: boolean;
  disabled?: boolean;
  blockedAgents?: ReadonlySet<AgentId>;
};

export const AskBar = forwardRef<AskBarHandle, AskBarProps>(function AskBar(
  {
    value: controlledValue,
    tag: controlledTag,
    onChangeText,
    onSubmit,
    onVoice,
    onAttach,
    hasAttachment,
    disabled,
    blockedAgents,
  },
  ref,
) {
  const { colors, radius, spacing, typography } = useTheme();
  const inputRef = useRef<TextInput>(null);
  useImperativeHandle(ref, () => ({ focus: () => inputRef.current?.focus() }), []);
  const [internalValue, setInternalValue] = useState('');
  const [internalTag, setInternalTag] = useState<AgentId | undefined>(undefined);

  const isControlled = controlledValue !== undefined && onChangeText !== undefined;
  const value = isControlled ? controlledValue! : internalValue;
  const tag = isControlled ? controlledTag : internalTag;

  const emit = useCallback(
    (next: AskBarChange) => {
      if (isControlled) {
        onChangeText!(next);
      } else {
        setInternalValue(next.text);
        setInternalTag(next.tag);
      }
    },
    [isControlled, onChangeText],
  );

  const handleChangeText = useCallback(
    (text: string) => {
      if (!tag) {
        const match = LEADING_TAG_RE.exec(text);
        if (match) {
          const candidate = match[1] as AgentId;
          if (!blockedAgents?.has(candidate)) {
            emit({ tag: candidate, text: match[2] ?? '' });
            return;
          }
        }
      }
      emit({ tag, text });
    },
    [emit, tag, blockedAgents],
  );

  const handleKeyPress = useCallback(
    (e: { nativeEvent: { key: string } }) => {
      if (e.nativeEvent.key === 'Backspace' && value === '' && tag) {
        emit({ tag: undefined, text: '' });
      }
    },
    [emit, tag, value],
  );

  const canSend = !!value.trim() || !!tag || !!hasAttachment;

  const send = () => {
    if (!canSend || disabled) return;
    onSubmit({ tag, text: value.trim() });
    emit({ tag: undefined, text: '' });
  };

  const circleSize = 36;

  return (
    <View
      style={[
        styles.bar,
        {
          backgroundColor: colors.bg2,
          borderColor: colors.border,
          borderRadius: radius.rXl,
          paddingLeft: spacing.s3,
          paddingRight: spacing.s2,
          paddingVertical: spacing.s2,
          marginHorizontal: spacing.s3,
          marginVertical: spacing.s2,
          opacity: disabled ? 0.55 : 1,
        },
      ]}
    >
      <Pressable
        testID="ask-attach"
        onPress={disabled ? undefined : onAttach}
        hitSlop={8}
        style={{ marginRight: spacing.s2 }}
      >
        <Icon name="Paperclip" size={20} color={colors.fg3} testID="ask-attach-icon" />
      </Pressable>
      {tag && (
        <View style={{ marginRight: 6 }}>
          <AgentChip
            agent={tag}
            tone="on-input"
            size="md"
            removable
            onRemove={() => emit({ tag: undefined, text: value })}
          />
        </View>
      )}
      <TextInput
        ref={inputRef}
        testID="ask-input"
        style={[
          typography.body,
          {
            color: colors.fg1,
            flex: 1,
            paddingTop: 0,
            paddingBottom: 0,
            textAlignVertical: 'center',
          },
        ]}
        placeholder={tag ? '' : 'Ask anything, or type /'}
        placeholderTextColor={colors.fg3}
        value={value}
        onChangeText={handleChangeText}
        onKeyPress={handleKeyPress}
        multiline
        blurOnSubmit={false}
        editable={!disabled}
      />
      {canSend ? (
        <Pressable
          testID="ask-send"
          onPress={send}
          hitSlop={4}
          style={[
            styles.circle,
            {
              width: circleSize,
              height: circleSize,
              borderRadius: circleSize / 2,
              backgroundColor: colors.accentHi,
            },
          ]}
        >
          <Icon
            name="PaperPlaneRight"
            size={18}
            color={colors.bg1}
            testID="ask-send-icon"
            weight="fill"
          />
        </Pressable>
      ) : (
        <Pressable
          testID="ask-mic"
          onPress={onVoice}
          hitSlop={4}
          style={[
            styles.circle,
            {
              width: circleSize,
              height: circleSize,
              borderRadius: circleSize / 2,
              backgroundColor: colors.bg3,
            },
          ]}
        >
          <Icon name="Microphone" size={18} color={colors.fg2} testID="ask-mic-icon" />
        </Pressable>
      )}
    </View>
  );
});

const styles = StyleSheet.create({
  bar: { alignItems: 'center', borderWidth: 1, flexDirection: 'row' },
  circle: { alignItems: 'center', justifyContent: 'center' },
});
