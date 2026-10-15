import * as Linking from 'expo-linking';
import type { OutgoingAttachment } from '@/features/chat/tasksApi';

const MIME: Record<string, string> = {
  pdf: 'application/pdf',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
  heic: 'image/heic',
};

/** A Share Extension link (`?shareFileURL=…&shareFileName=…`) as a task attachment. */
export function shareAttachment(url: string): OutgoingAttachment | null {
  const { queryParams } = Linking.parse(url);
  const uri = queryParams?.shareFileURL;
  const name = queryParams?.shareFileName;
  if (typeof uri !== 'string' || typeof name !== 'string' || !uri || !name) return null;
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  return { uri, name, mime: MIME[ext] ?? 'application/octet-stream', size: 0 };
}
