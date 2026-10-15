import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { CameraDenied, pickAttachments, validateAttachments } from './attachments';

const img = (size: number, mime = 'image/jpeg') => ({
  uri: 'file:///a.jpg',
  name: 'a.jpg',
  mime,
  size,
});
const pdf = (size: number) => ({
  uri: 'file:///a.pdf',
  name: 'a.pdf',
  mime: 'application/pdf',
  size,
});

test.each([
  [[img(1)], { ok: true }],
  [[img(1), img(1), img(1), img(1), img(1)], { ok: false, reason: 'too_many' }],
  [[img(1, 'image/heic')], { ok: false, reason: 'type' }],
  [[img(10_000_001)], { ok: false, reason: 'image_too_big' }],
  [[pdf(20_000_001)], { ok: false, reason: 'pdf_too_big' }],
  [[pdf(15_000_000), img(9_000_000), img(2_000_000)], { ok: false, reason: 'total_too_big' }],
  [[pdf(20_000_000), img(5_000_000)], { ok: true }],
])('validate %#', (list, expected) => {
  expect(validateAttachments(list)).toEqual(expected);
});

test('gallery results become attachments; unknown mime falls back by extension', async () => {
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValueOnce({
    canceled: false,
    assets: [
      { uri: 'file:///x/IMG_1.PNG', fileName: 'IMG_1.PNG', mimeType: undefined, fileSize: 1200 },
      { uri: 'file:///x/2.jpg', fileName: null, mimeType: 'image/jpeg', fileSize: 800 },
    ],
  });
  const got = await pickAttachments('gallery', 3);
  expect(ImagePicker.launchImageLibraryAsync).toHaveBeenCalledWith(
    expect.objectContaining({ allowsMultipleSelection: true, selectionLimit: 3, quality: 0.8 }),
  );
  expect(got).toEqual([
    { uri: 'file:///x/IMG_1.PNG', name: 'IMG_1.PNG', mime: 'image/png', size: 1200 },
    {
      uri: 'file:///x/2.jpg',
      name: expect.stringMatching(/^photo-.*\.jpg$/),
      mime: 'image/jpeg',
      size: 800,
    },
  ]);
});

test('camera without permission throws CameraDenied', async () => {
  (ImagePicker.requestCameraPermissionsAsync as jest.Mock).mockResolvedValueOnce({
    granted: false,
  });
  await expect(pickAttachments('camera', 4)).rejects.toBeInstanceOf(CameraDenied);
});

test('file picks one PDF', async () => {
  (DocumentPicker.getDocumentAsync as jest.Mock).mockResolvedValueOnce({
    canceled: false,
    assets: [{ uri: 'file:///s.pdf', name: 's.pdf', size: 5000 }],
  });
  expect(await pickAttachments('file', 4)).toEqual([
    { uri: 'file:///s.pdf', name: 's.pdf', mime: 'application/pdf', size: 5000 },
  ]);
});

test.each([0, 10_000_000])('image byte boundary %s is accepted', (size) =>
  expect(validateAttachments([img(size)])).toEqual({ ok: true }),
);
test.each([NaN, Infinity, -1])('invalid size %s is refused', (size) =>
  expect(validateAttachments([img(size)]).ok).toBe(false),
);
test('missing picker metadata never turns an unknown format into JPEG', async () => {
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValueOnce({
    canceled: false,
    assets: [{ uri: 'file:///unknown.blob' }],
  });
  const got = await pickAttachments('gallery', 4);
  expect(got[0]?.size).toBe(0);
  expect(validateAttachments(got)).toEqual({ ok: false, reason: 'type' });
});
test('picker excess is returned for full validation rather than silently truncated', async () => {
  (ImagePicker.launchImageLibraryAsync as jest.Mock).mockResolvedValueOnce({
    canceled: false,
    assets: Array.from({ length: 5 }, () => ({ uri: 'file:///a.jpg', fileSize: 1 })),
  });
  expect(validateAttachments(await pickAttachments('gallery', 4))).toEqual({
    ok: false,
    reason: 'too_many',
  });
});
test('file picker does not relabel an unsupported result as PDF', async () => {
  (DocumentPicker.getDocumentAsync as jest.Mock).mockResolvedValueOnce({
    canceled: false,
    assets: [
      { uri: 'file:///x.exe', name: 'x.exe', mimeType: 'application/octet-stream', size: 1 },
    ],
  });
  expect(validateAttachments(await pickAttachments('file', 4))).toEqual({
    ok: false,
    reason: 'type',
  });
});
