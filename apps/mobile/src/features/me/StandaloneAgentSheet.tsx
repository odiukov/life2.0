import React from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { appLocale } from '@/lib/locale';
import { AgentDetailContent } from '../home/AgentDetailContent';
import { openTask } from '../task/sheetStore';

const BACKDROP_COLOR = 'rgba(0,0,0,0.6)';

/** Body/Home retain their existing details without becoming pager pages. */
export function StandaloneAgentSheet({
  agent,
  onClose,
}: {
  agent: 'body' | 'home' | null;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const t = useT(appLocale());
  if (!agent) return null;
  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={onClose}
          accessibilityLabel={t('me.close_details')}
        />
        <View style={[styles.sheet, { backgroundColor: colors.bg1 }]}>
          <Pressable onPress={onClose} style={styles.close} accessibilityRole="button">
            <Text style={{ color: colors.fg1 }}>{t('me.close_details')}</Text>
          </Pressable>
          <ScrollView contentContainerStyle={styles.content}>
            <AgentDetailContent
              agentId={agent}
              onAction={(message) => {
                onClose();
                openTask({ lead: agent, send: message });
              }}
            />
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}
const styles = StyleSheet.create({
  close: { alignSelf: 'flex-end', padding: 16 },
  content: { padding: 16, paddingBottom: 48 },
  overlay: { backgroundColor: BACKDROP_COLOR, flex: 1, justifyContent: 'flex-end' },
  sheet: { borderTopLeftRadius: 22, borderTopRightRadius: 22, height: '88%', overflow: 'hidden' },
});
