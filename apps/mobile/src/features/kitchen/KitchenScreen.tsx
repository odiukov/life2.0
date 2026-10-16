import React, { useCallback, useEffect, useState } from 'react';
// eslint-disable-next-line react-native/split-platform-components
import { ActionSheetIOS, Alert, Modal, Platform, Pressable, Text, TextInput, View } from 'react-native';
import DateTimePicker from '@react-native-community/datetimepicker';
import { useTheme } from '@life-agents/ui';
import { useT } from '@life-agents/i18n';
import { errorCode } from '@/api/gateway';
import { useHousehold } from '@/features/household/useHousehold';
import { appLocale } from '@/lib/locale';
import { openTask } from '../task/sheetStore';
import { daysLeft, expiryLabel, expiryTone } from './expiry';
import { UndoSnackbar } from './UndoSnackbar';
import { type ItemAction, type KitchenItem, type Location, useInventory, useKitchenActions } from './useKitchen';

const LOCATIONS: Location[] = ['fridge', 'freezer', 'pantry'];
const ACTIONS: ItemAction['action'][] = ['consumed', 'discarded', 'opened', 'move', 'set_expiry', 'set_quantity'];
const pad = (n: number) => String(n).padStart(2, '0');
const localIso = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

export function KitchenPanel() {
  const { colors, spacing, typography } = useTheme();
  const t = useT(appLocale());

  const household = useHousehold();
  const [location, setLocation] = useState<Location>('fridge');
  const inventory = useInventory(location, household.data?.id);
  const { act, undo } = useKitchenActions();
  const [snack, setSnack] = useState<{ label: string; groupId: string } | null>(null);
  const [dating, setDating] = useState<KitchenItem | null>(null);
  const [editingQuantity, setEditingQuantity] = useState<KitchenItem | null>(null);
  const [quantityText, setQuantityText] = useState('');

  const { refetch: refetchHousehold } = household;
  const { refetch: refetchInventory } = inventory;
  useEffect(() => {
    void refetchHousehold();
  }, [refetchHousehold]);
  const householdId = household.data?.id;
  useEffect(() => {
    if (householdId) void refetchInventory();
  }, [householdId, refetchInventory]);

  const run = async (item: KitchenItem, body: ItemAction) => {
    try {
      const result = await act.mutateAsync({ id: item.id, body });
      setSnack({ label: t(`kitchen.screen.done.${body.action}`, { name: item.display_name }), groupId: result.group_id });
    } catch (error) {
      Alert.alert(errorCode(error) === 'item_gone' ? t('kitchen.screen.gone') : t('kitchen.screen.unavailable'));
    }
  };

  const choose = (title: string, labels: string[], callback: (index: number) => void) => {
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions({ title, options: [...labels, t('kitchen.screen.actions.cancel')], cancelButtonIndex: labels.length }, callback);
    } else {
      Alert.alert(title, undefined, [...labels.map((label, index) => ({ text: label, onPress: () => callback(index) })), { text: t('kitchen.screen.actions.cancel'), style: 'cancel' }]);
    }
  };

  const openActions = (item: KitchenItem) => {
    choose(item.display_name, ACTIONS.map((action) => t(`kitchen.screen.actions.${action}`)), (index) => {
      const action = ACTIONS[index];
      if (!action) return;
      if (action === 'move') {
        const targets = LOCATIONS.filter((target) => target !== item.location);
        choose(item.display_name, targets.map((target) => t(`kitchen.screen.${target}`)), (targetIndex) => {
          if (targets[targetIndex]) void run(item, { action: 'move', location: targets[targetIndex] });
        });
      } else if (action === 'set_expiry') {
        setDating(item);
      } else if (action === 'set_quantity') {
        setQuantityText(item.quantity);
        setEditingQuantity(item);
      } else {
        void run(item, { action });
      }
    });
  };

  const toneColor = { danger: colors.danger, warn: colors.warn, muted: colors.fg3 } as const;
  const timezone = household.data?.timezone;
  const errored = inventory.isError || household.isError;
  const loading = inventory.isLoading || household.isLoading || !timezone;
  const items = [...(inventory.data?.items ?? [])].sort((a, b) => a.expires_on.localeCompare(b.expires_on));
  const hideSnack = useCallback(() => setSnack(null), []);

  return (
    <View>
      <Text style={[typography.title2, { color: colors.fg1, padding: spacing.s4 }]}>{t('kitchen.screen.title')}</Text>
      <View style={{ flexDirection: 'row', gap: spacing.s2, paddingHorizontal: spacing.s4 }}>
        {LOCATIONS.map((l) => (
          <Pressable key={l} onPress={() => setLocation(l)} accessibilityRole="tab" accessibilityLabel={t(`kitchen.screen.${l}`)} accessibilityState={{ selected: l === location }} style={{ paddingVertical: 6, paddingHorizontal: 12, borderRadius: 999, backgroundColor: l === location ? colors.bg3 : undefined }}>
            <Text style={{ color: l === location ? colors.fg1 : colors.fg3 }}>{t(`kitchen.screen.${l}`)}</Text>
          </Pressable>
        ))}
      </View>
      {errored ? (
        <View style={{ padding: spacing.s4, gap: spacing.s3 }}>
          <Text style={{ color: colors.fg2 }}>{t('kitchen.screen.unavailable')}</Text>
          <Pressable onPress={() => { void household.refetch(); void inventory.refetch(); }} accessibilityRole="button" accessibilityLabel={t('kitchen.screen.retry')}><Text style={{ color: colors.accentHi }}>{t('kitchen.screen.retry')}</Text></Pressable>
        </View>
      ) : (
        <View style={{ padding: spacing.s4, gap: spacing.s2 }}>
          {loading ? null : items.length === 0 ? (
            <View style={{ gap: spacing.s3 }}>
              <Text style={{ color: colors.fg3 }}>{t('kitchen.screen.empty')}</Text>
              <Pressable onPress={() => openTask({ lead: 'kitchen' })} accessibilityRole="button" accessibilityLabel={t('kitchen.screen.open_chat')}><Text style={{ color: colors.accentHi }}>{t('kitchen.screen.open_chat')}</Text></Pressable>
            </View>
          ) : items.map((item) => {
            const days = daysLeft(item.expires_on, new Date(), timezone);
            const mark = item.expiry_source === 'estimated' ? `${t('kitchen.screen.estimated')} ` : '';
            return (
              <View key={item.id} testID={`kitchen-item-${item.id}`}>
                <Pressable onPress={() => openActions(item)} onLongPress={() => openActions(item)} accessibilityRole="button" accessibilityLabel={item.display_name} accessibilityHint={t('kitchen.screen.actions_hint')}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between', padding: spacing.s3, backgroundColor: colors.bg2, borderRadius: 12 }}>
                    <Text style={[typography.bodyEm, { color: colors.fg1, flex: 1 }]}>{item.display_name}</Text>
                    <Text style={{ color: toneColor[expiryTone(days)] }}>{mark}{expiryLabel(days, t)}</Text>
                  </View>
                </Pressable>
              </View>
            );
          })}
        </View>
      )}
      {dating && <DateTimePicker value={new Date(`${dating.expires_on}T12:00:00`)} mode="date" onChange={(_, date) => {
        const item = dating;
        setDating(null);
        if (date) void run(item, { action: 'set_expiry', expires_on: localIso(date) });
      }} />}
      <Modal visible={editingQuantity !== null} transparent animationType="fade" onRequestClose={() => setEditingQuantity(null)}>
        <View style={{ flex: 1, justifyContent: 'center', padding: spacing.s4, backgroundColor: colors.bg0 }}>
          <View style={{ padding: spacing.s4, gap: spacing.s3, borderRadius: 12, backgroundColor: colors.bg2 }}>
            <Text style={{ color: colors.fg1 }}>{t('kitchen.screen.quantity_prompt', { unit: t(`kitchen.units.${editingQuantity?.unit ?? 'pcs'}`) })}</Text>
            <TextInput value={quantityText} onChangeText={setQuantityText} keyboardType="decimal-pad" style={{ color: colors.fg1, borderColor: colors.border, borderWidth: 1, padding: spacing.s3 }} />
            <View style={{ flexDirection: 'row', gap: spacing.s4 }}>
              <Pressable onPress={() => setEditingQuantity(null)}><Text style={{ color: colors.fg2 }}>{t('kitchen.screen.actions.cancel')}</Text></Pressable>
              <Pressable onPress={() => {
                const item = editingQuantity;
                const quantity = Number(quantityText.replace(',', '.'));
                if (item && Number.isFinite(quantity) && quantity > 0) {
                  setEditingQuantity(null);
                  void run(item, { action: 'set_quantity', quantity: String(quantity) });
                }
              }}><Text style={{ color: colors.accentHi }}>{t('kitchen.screen.actions.save')}</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>
      <UndoSnackbar visible={snack !== null} label={snack?.label ?? ''} undoLabel={t('kitchen.screen.undo')} onUndo={() => {
        if (snack) void undo.mutateAsync(snack.groupId).catch((error: unknown) => Alert.alert(errorCode(error) === 'conflict' ? t('kitchen.undo_conflict') : t('kitchen.screen.unavailable')));
        setSnack(null);
      }} onHide={hideSnack} actionId={snack?.groupId} />
    </View>
  );
}
