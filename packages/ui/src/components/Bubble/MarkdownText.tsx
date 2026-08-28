import React from 'react';
import { Text, View, StyleSheet } from 'react-native';

interface Props {
  children: string;
  color: string;
  fontSize?: number;
  lineHeight?: number;
}

// Returns inline Text spans — must be used inside a parent <Text>
function renderInline(text: string, color: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith('**') && part.endsWith('**')
      ? <Text key={i} style={{ fontWeight: '700', color }}>{part.slice(2, -2)}</Text>
      : <Text key={i} style={{ color }}>{part}</Text>
  );
}

export function MarkdownText({ children, color, fontSize = 14, lineHeight = 21 }: Props) {
  const lines = children.split('\n');
  const nodes: React.ReactNode[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i] ?? '';

    const headingMatch = line.match(/^(#{1,3})\s+(.+)/);
    if (headingMatch) {
      const level = headingMatch[1]!.length;
      const sizes: [number, number, number] = [fontSize + 4, fontSize + 2, fontSize];
      nodes.push(
        <Text key={i} style={[styles.heading, { color, fontSize: sizes[level - 1]!, lineHeight: sizes[level - 1]! * 1.5 }]}>
          {headingMatch[2]}
        </Text>
      );
      continue;
    }

    const bulletMatch = line.match(/^[-*]\s+(.*)/);
    if (bulletMatch) {
      nodes.push(
        <Text key={i} style={{ color, fontSize, lineHeight, marginVertical: 1 }}>
          {'• '}{renderInline(bulletMatch[1] ?? '', color)}
        </Text>
      );
      continue;
    }

    const numberedMatch = line.match(/^(\d+)\.\s+(.*)/);
    if (numberedMatch) {
      nodes.push(
        <Text key={i} style={{ color, fontSize, lineHeight, marginVertical: 1 }}>
          {(numberedMatch[1] ?? '') + '. '}{renderInline(numberedMatch[2] ?? '', color)}
        </Text>
      );
      continue;
    }

    if (line.trim() === '') {
      nodes.push(<View key={i} style={styles.spacer} />);
      continue;
    }

    nodes.push(
      <Text key={i} style={{ color, fontSize, lineHeight }}>
        {renderInline(line, color)}
      </Text>
    );
  }

  return <>{nodes}</>;
}

const styles = StyleSheet.create({
  heading: { fontWeight: '700', marginTop: 6, marginBottom: 2 },
  spacer: { height: 6 },
});
