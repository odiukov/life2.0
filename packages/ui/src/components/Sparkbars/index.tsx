import React from 'react';
import { View } from 'react-native';

interface SparkbarsProps {
  values: number[];
  color: string;
  height?: number;
  testID?: string;
  target?: number;
  targetColor?: string;
}

export function Sparkbars({
  values,
  color,
  height = 28,
  testID,
  target,
  targetColor = '#8a8a8a',
}: SparkbarsProps) {
  const max = Math.max(...values, target ?? 0, 1);
  const targetTop = target !== undefined ? height - (target / max) * height : null;
  return (
    <View testID={testID} style={{ position: 'relative', height, justifyContent: 'flex-end' }}>
      <View style={{ flexDirection: 'row', alignItems: 'flex-end', height, gap: 3 }}>
        {values.map((v, i) => {
          const opacity = i === values.length - 1 ? 1 : 0.45 + (i / values.length) * 0.4;
          return (
            <View
              key={i}
              style={{
                flex: 1,
                height: Math.max(2, (v / max) * height),
                backgroundColor: color,
                borderRadius: 1,
                opacity,
              }}
            />
          );
        })}
      </View>
      {targetTop !== null && (
        <View
          pointerEvents="none"
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: targetTop,
            height: 1,
            backgroundColor: targetColor,
            opacity: 0.6,
          }}
        />
      )}
    </View>
  );
}
