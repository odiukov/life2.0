import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import type { OutgoingAttachment } from '@/features/chat/tasksApi';

export const LIMITS = {
  count: 4,
  imageBytes: 10_000_000,
  pdfBytes: 20_000_000,
  totalBytes: 25_000_000,
} as const;
const IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const PDF = 'application/pdf';

export type AttachmentProblem =
  | 'too_many'
  | 'type'
  | 'image_too_big'
  | 'pdf_too_big'
  | 'total_too_big';
export type Source = 'camera' | 'gallery' | 'file';
export class CameraDenied extends Error {}

/** The server's limits (3c §6.4), checked before upload so the reason can be shown. */
export function validateAttachments(
  list: readonly OutgoingAttachment[],
): { ok: true } | { ok: false; reason: AttachmentProblem } {
  if (list.length > LIMITS.count) return { ok: false, reason: 'too_many' };
  let total = 0;
  for (const a of list) {
    if (a.mime === PDF) {
      if (a.size > LIMITS.pdfBytes) return { ok: false, reason: 'pdf_too_big' };
    } else if (IMAGE_TYPES.has(a.mime)) {
      if (a.size > LIMITS.imageBytes) return { ok: false, reason: 'image_too_big' };
    } else {
      return { ok: false, reason: 'type' };
    }
    if (!Number.isFinite(a.size) || a.size < 0) return { ok: false, reason: 'total_too_big' };
    total += a.size;
  }
  return total > LIMITS.totalBytes ? { ok: false, reason: 'total_too_big' } : { ok: true };
}

function imageMime(mime: string | null | undefined, uri: string): string {
  if (mime) return mime.toLowerCase();
  const ext = uri.split('.').pop()?.toLowerCase();
  if (ext === 'png') return 'image/png';
  if (ext === 'webp') return 'image/webp';
  if (ext === 'heic' || ext === 'heif') return 'image/heic';
  if (ext === 'jpg' || ext === 'jpeg') return 'image/jpeg';
  return 'application/octet-stream';
}

let counter = 0;

export async function pickAttachments(source: Source, room: number): Promise<OutgoingAttachment[]> {
  if (room <= 0) return [];
  if (source === 'file') {
    const result = await DocumentPicker.getDocumentAsync({ type: PDF, copyToCacheDirectory: true });
    const asset = result.assets?.[0];
    return result.canceled || !asset
      ? []
      : [
          {
            uri: asset.uri,
            name: asset.name,
            mime:
              asset.mimeType?.toLowerCase() ??
              (/\.pdf$/i.test(asset.name) ? PDF : 'application/octet-stream'),
            size: asset.size ?? 0,
          },
        ];
  }
  if (source === 'camera') {
    const permission = await ImagePicker.requestCameraPermissionsAsync();
    if (!permission.granted) throw new CameraDenied();
  }
  const options = { mediaTypes: ['images'] as ImagePicker.MediaType[], quality: 0.8 };
  const result =
    source === 'camera'
      ? await ImagePicker.launchCameraAsync(options)
      : await ImagePicker.launchImageLibraryAsync({
          ...options,
          allowsMultipleSelection: room > 1,
          selectionLimit: room,
        });
  if (result.canceled || !result.assets) return [];
  return result.assets.map((a) => ({
    uri: a.uri,
    name: a.fileName ?? `photo-${Date.now()}-${counter++}.jpg`,
    mime: imageMime(a.mimeType, a.uri),
    size: a.fileSize ?? 0,
  }));
}
