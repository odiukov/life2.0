import React, { useState, useEffect } from 'react';
import { Modal, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import Animated from 'react-native-reanimated';
import { GestureDetector, GestureHandlerRootView } from 'react-native-gesture-handler';
import { useTheme } from '@life-agents/ui';
import { useSheetAnimation } from '@/lib/sheetAnimation';
import { useSwipeToDismiss } from '@/lib/useSwipeToDismiss';
import { api } from '@/api/client';
import * as DocumentPicker from 'expo-document-picker';
import { supabase, SUPABASE_CONFIGURED } from '@/features/auth/SupabaseClient';
import { apiBaseUrl } from '@/api/client';

type ActivityLevel = 'sedentary' | 'light' | 'moderate' | 'active' | 'very_active';
const ACTIVITY_LEVELS: { key: ActivityLevel; label: string }[] = [
  { key: 'sedentary', label: 'Sedentary' },
  { key: 'light', label: 'Light' },
  { key: 'moderate', label: 'Moderate' },
  { key: 'active', label: 'Active' },
  { key: 'very_active', label: 'Very active' },
];

type Props = {
  visible: boolean;
  onClose: () => void;
  onSaved: () => void;
};

export function BodyProfileSheet({ visible, onClose, onSaved }: Props) {
  const { colors, radius, spacing, typography } = useTheme();
  const { mounted, sheetY, backdropAlpha, backdropStyle, sheetStyle } = useSheetAnimation(visible);
  const { panGesture, scrollHandler } = useSwipeToDismiss({
    sheetY,
    backdropAlpha,
    onClose,
  });

  const [heightCm, setHeightCm] = useState('');
  const [weightKg, setWeightKg] = useState('');
  const [age, setAge] = useState('');
  const [sex, setSex] = useState<'male' | 'female' | null>(null);
  const [activityLevel, setActivityLevel] = useState<ActivityLevel>('moderate');
  const [calorieOverride, setCalorieOverride] = useState('');
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) return;
    api.GET('/me/profile').then(({ data }) => {
      if (!data) return;
      if (data.height_cm != null) setHeightCm(String(data.height_cm));
      if (data.weight_kg != null) setWeightKg(String(data.weight_kg));
      if (data.age != null) setAge(String(data.age));
      if (data.sex != null) setSex(data.sex as 'male' | 'female');
      if (data.activity_level != null) setActivityLevel(data.activity_level as ActivityLevel);
      if (data.calorie_goal_override != null)
        setCalorieOverride(String(data.calorie_goal_override));
    });
  }, [visible]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await api.PATCH('/me/profile', {
        body: {
          height_cm: heightCm ? parseFloat(heightCm) : undefined,
          weight_kg: weightKg ? parseFloat(weightKg) : undefined,
          age: age ? parseInt(age, 10) : undefined,
          sex: sex ?? undefined,
          activity_level: activityLevel,
          calorie_goal_override: calorieOverride ? parseInt(calorieOverride, 10) : null,
        },
      });
      onSaved();
      onClose();
    } catch {
      setError('Failed to save. Please try again.');
    } finally {
      setSaving(false);
    }
  }

  async function handleImportPdf() {
    const picked = await DocumentPicker.getDocumentAsync({ type: 'application/pdf' });
    if (picked.canceled || !picked.assets?.[0]) return;

    setImporting(true);
    setError(null);
    try {
      const asset = picked.assets[0];
      const formData = new FormData();
      formData.append('file', {
        uri: asset.uri,
        name: asset.name ?? 'vihealth.pdf',
        type: 'application/pdf',
      } as any);

      let token: string | undefined;
      if (SUPABASE_CONFIGURED) {
        const { data } = await supabase.auth.getSession();
        token = data.session?.access_token;
      }

      const response = await fetch(`${apiBaseUrl}/me/profile/import-pdf`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`${response.status}`);
      }

      const imported = (await response.json()) as {
        height_cm?: number | null;
        weight_kg?: number | null;
        age?: number | null;
        sex?: 'male' | 'female' | null;
      };

      if (imported.height_cm != null) setHeightCm(String(imported.height_cm));
      if (imported.weight_kg != null) setWeightKg(String(imported.weight_kg));
      if (imported.age != null) setAge(String(imported.age));
      if (imported.sex != null) setSex(imported.sex);
    } catch {
      setError('Could not read PDF. Please try again.');
    } finally {
      setImporting(false);
    }
  }

  if (!mounted) return null;

  return (
    <Modal
      visible={mounted}
      transparent
      animationType="none"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <GestureHandlerRootView style={{ flex: 1 }}>
        <View style={styles.overlay}>
          <Animated.View style={[styles.backdrop, backdropStyle]} pointerEvents="none" />
          <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />

          <GestureDetector gesture={panGesture}>
            <Animated.ScrollView
              style={[styles.sheet, { backgroundColor: colors.bg2 }, sheetStyle]}
              contentContainerStyle={{ padding: spacing.s4, paddingBottom: 40 }}
              keyboardShouldPersistTaps="handled"
              onScroll={scrollHandler}
              scrollEventThrottle={16}
            >
              <View style={styles.handle} />
              <Text style={[typography.title1, { color: colors.fg1, marginBottom: 4 }]}>
                Body Profile
              </Text>
              <Text style={[typography.caption, { color: colors.fg3, marginBottom: spacing.s4 }]}>
                Used to calculate your daily calorie goal
              </Text>

              <Pressable
                onPress={handleImportPdf}
                disabled={importing}
                style={[
                  styles.importBtn,
                  {
                    borderColor: colors.border,
                    borderRadius: radius.rSm,
                    opacity: importing ? 0.6 : 1,
                  },
                ]}
              >
                <Text style={[typography.caption, { color: colors.fg2, textAlign: 'center' }]}>
                  {importing ? 'Reading PDF…' : 'Import from ViHealth PDF'}
                </Text>
              </Pressable>

              <View style={styles.row}>
                <View style={styles.half}>
                  <Text style={[typography.micro, { color: colors.fg3, marginBottom: 4 }]}>
                    HEIGHT (CM)
                  </Text>
                  <TextInput
                    style={[
                      styles.input,
                      {
                        backgroundColor: colors.bg1,
                        color: colors.fg1,
                        borderRadius: radius.rSm,
                        borderColor: colors.border,
                      },
                    ]}
                    value={heightCm}
                    onChangeText={setHeightCm}
                    keyboardType="numeric"
                    placeholder="182"
                    placeholderTextColor={colors.fg3}
                  />
                </View>
                <View style={styles.half}>
                  <Text style={[typography.micro, { color: colors.fg3, marginBottom: 4 }]}>
                    WEIGHT (KG)
                  </Text>
                  <TextInput
                    style={[
                      styles.input,
                      {
                        backgroundColor: colors.bg1,
                        color: colors.fg1,
                        borderRadius: radius.rSm,
                        borderColor: colors.border,
                      },
                    ]}
                    value={weightKg}
                    onChangeText={setWeightKg}
                    keyboardType="numeric"
                    placeholder="78 · auto"
                    placeholderTextColor={colors.fg3}
                  />
                </View>
              </View>

              <View style={styles.row}>
                <View style={styles.half}>
                  <Text style={[typography.micro, { color: colors.fg3, marginBottom: 4 }]}>
                    AGE
                  </Text>
                  <TextInput
                    style={[
                      styles.input,
                      {
                        backgroundColor: colors.bg1,
                        color: colors.fg1,
                        borderRadius: radius.rSm,
                        borderColor: colors.border,
                      },
                    ]}
                    value={age}
                    onChangeText={setAge}
                    keyboardType="numeric"
                    placeholder="28"
                    placeholderTextColor={colors.fg3}
                  />
                </View>
                <View style={styles.half}>
                  <Text style={[typography.micro, { color: colors.fg3, marginBottom: 4 }]}>
                    SEX
                  </Text>
                  <View style={styles.toggleRow}>
                    {(['male', 'female'] as const).map((s) => (
                      <Pressable
                        key={s}
                        onPress={() => setSex(s)}
                        style={[
                          styles.toggleBtn,
                          { borderRadius: radius.rXs, borderColor: colors.border },
                          sex === s && { backgroundColor: '#6366f1', borderColor: '#6366f1' },
                        ]}
                      >
                        <Text
                          style={[typography.micro, { color: sex === s ? '#fff' : colors.fg3 }]}
                        >
                          {s === 'male' ? 'M' : 'F'}
                        </Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
              </View>

              <Text
                style={[
                  typography.micro,
                  { color: colors.fg3, marginBottom: 6, marginTop: spacing.s2 },
                ]}
              >
                ACTIVITY LEVEL
              </Text>
              <View style={styles.activityRow}>
                {ACTIVITY_LEVELS.map(({ key, label }) => (
                  <Pressable
                    key={key}
                    onPress={() => setActivityLevel(key)}
                    style={[
                      styles.activityBtn,
                      { borderRadius: radius.rXs, borderColor: colors.border },
                      activityLevel === key && {
                        backgroundColor: '#6366f1',
                        borderColor: '#6366f1',
                      },
                    ]}
                  >
                    <Text
                      style={[
                        typography.micro,
                        { color: activityLevel === key ? '#fff' : colors.fg3 },
                      ]}
                    >
                      {label}
                    </Text>
                  </Pressable>
                ))}
              </View>

              <Text
                style={[
                  typography.micro,
                  { color: colors.fg3, marginBottom: 4, marginTop: spacing.s3 },
                ]}
              >
                CALORIE GOAL OVERRIDE (OPTIONAL)
              </Text>
              <TextInput
                style={[
                  styles.input,
                  {
                    backgroundColor: colors.bg1,
                    color: colors.fg1,
                    borderRadius: radius.rSm,
                    borderColor: colors.border,
                  },
                ]}
                value={calorieOverride}
                onChangeText={setCalorieOverride}
                keyboardType="numeric"
                placeholder="Leave empty — auto from TDEE"
                placeholderTextColor={colors.fg3}
              />

              {error && (
                <Text
                  style={[
                    typography.micro,
                    { color: '#f87171', marginBottom: 8, textAlign: 'center' },
                  ]}
                >
                  {error}
                </Text>
              )}

              <Pressable
                onPress={handleSave}
                disabled={saving}
                style={[
                  styles.saveBtn,
                  {
                    backgroundColor: '#6366f1',
                    borderRadius: radius.rMd,
                    marginTop: spacing.s4,
                    opacity: saving ? 0.6 : 1,
                  },
                ]}
              >
                <Text
                  style={[
                    typography.body,
                    { color: '#fff', fontWeight: '600', textAlign: 'center' },
                  ]}
                >
                  {saving ? 'Saving…' : 'Save'}
                </Text>
              </Pressable>

              <Text
                style={[
                  typography.micro,
                  { color: colors.fg3, textAlign: 'center', marginTop: spacing.s2 },
                ]}
              >
                You can also update this via chat anytime
              </Text>
            </Animated.ScrollView>
          </GestureDetector>
        </View>
      </GestureHandlerRootView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.6)' },
  sheet: { borderTopLeftRadius: 20, borderTopRightRadius: 20, maxHeight: '85%' },
  handle: {
    width: 36,
    height: 4,
    backgroundColor: '#334155',
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: 16,
  },
  row: { flexDirection: 'row', gap: 12, marginBottom: 12 },
  half: { flex: 1 },
  input: { paddingHorizontal: 12, paddingVertical: 10, borderWidth: 1, fontSize: 14 },
  toggleRow: { flexDirection: 'row', gap: 8 },
  toggleBtn: { flex: 1, paddingVertical: 10, alignItems: 'center', borderWidth: 1 },
  activityRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  activityBtn: { paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1 },
  saveBtn: { paddingVertical: 14 },
  importBtn: { paddingVertical: 10, borderWidth: 1, alignItems: 'center', marginBottom: 16 },
});
