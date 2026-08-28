import { passthroughChatUrl, chatStreamUrl } from './client';

test('passthroughChatUrl returns /agent/<name>/stream relative to base', () => {
  expect(passthroughChatUrl('sleep')).toMatch(/\/agent\/sleep\/stream$/);
});

test('chatStreamUrl returns /chat/stream', () => {
  expect(chatStreamUrl()).toMatch(/\/chat\/stream$/);
});
