import React from 'react';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { Pressable, StyleSheet, Text } from 'react-native';
import { useTheme } from '@life-agents/ui';

type Props = {
  onPress: () => void;
};

export function BodyProfileAlert({ onPress }: Props) {
  const t = useT(appLocale());
  const { typography } = useTheme();
  return (
    <Pressable style={styles.banner} onPress={onPress}>
      <Text style={[typography.micro, styles.text]}>{t('me.body_profile')}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  banner: {
    backgroundColor: 'rgba(245,158,11,0.12)',
    borderColor: 'rgba(245,158,11,0.3)',
    borderRadius: 7,
    borderWidth: 1,
    marginTop: 7,
    paddingHorizontal: 7,
    paddingVertical: 5,
  },
  text: {
    color: '#fbbf24',
  },
});
