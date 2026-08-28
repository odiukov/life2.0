import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { useTheme } from '../../theme';
import { MarkdownText } from './MarkdownText';
import { TypingDots } from './TypingDots';
import { AgentChip } from '../AgentChip';
import type { AgentId } from '../AgentBadge';

export type BubbleSegment = string | { tag: AgentId };

interface BubbleProps {
  variant: 'user' | 'assistant';
  children?: React.ReactNode;
  segments?: readonly BubbleSegment[];
  loading?: boolean;
  testID?: string;
}

export function Bubble({ variant, children, segments, loading, testID }: BubbleProps) {
  const { colors } = useTheme();

  const hasContent =
    (segments && segments.length > 0) || (children !== undefined && children !== '');

  const body =
    loading && !hasContent ? (
      <TypingDots />
    ) : segments && segments.length > 0 ? (
      <SegmentRow segments={segments} variant={variant} />
    ) : variant === 'user' ? (
      <Text style={{ color: colors.accentInk, fontSize: 14, fontWeight: '500', lineHeight: 20 }}>
        {children}
      </Text>
    ) : (
      <MarkdownText color={colors.fg1}>{typeof children === 'string' ? children : ''}</MarkdownText>
    );

  if (variant === 'user') {
    return (
      <View
        testID={testID}
        style={[
          styles.userBubble,
          { backgroundColor: colors.accent, alignSelf: 'flex-end', maxWidth: '82%' },
        ]}
      >
        {body}
      </View>
    );
  }
  return (
    <View
      testID={testID}
      style={[
        styles.assistantBubble,
        {
          backgroundColor: colors.bg2,
          borderColor: colors.border,
          alignSelf: 'flex-start',
          maxWidth: '86%',
        },
      ]}
    >
      {body}
    </View>
  );
}

function SegmentRow({
  segments,
  variant,
}: {
  segments: readonly BubbleSegment[];
  variant: 'user' | 'assistant';
}) {
  const { colors } = useTheme();
  const tone = variant === 'user' ? 'on-user-bubble' : 'on-bubble';
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center' }}>
      {segments.map((seg, i) =>
        typeof seg === 'string' ? (
          variant === 'user' ? (
            <Text
              key={i}
              style={{ color: colors.accentInk, fontSize: 14, fontWeight: '500', lineHeight: 20 }}
            >
              {seg.trim()}{' '}
            </Text>
          ) : (
            <MarkdownText key={i} color={colors.fg1}>
              {seg.trim()}
            </MarkdownText>
          )
        ) : (
          <View key={i} style={{ marginRight: 4 }}>
            <AgentChip agent={seg.tag} tone={tone} size="sm" />
          </View>
        ),
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  userBubble: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    borderBottomRightRadius: 4,
  },
  assistantBubble: {
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 18,
    borderTopLeftRadius: 4,
    borderWidth: 1,
  },
});
