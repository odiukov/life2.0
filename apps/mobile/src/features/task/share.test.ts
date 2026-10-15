import * as Linking from 'expo-linking';
import { shareAttachment } from './share';

test('a share link becomes an attachment', () => {
  jest
    .spyOn(Linking, 'parse')
    .mockReturnValueOnce({
      queryParams: { shareFileURL: 'file:///s/Statement.PDF', shareFileName: 'Statement.PDF' },
    } as never);
  expect(shareAttachment('lifeagents://share?x')).toEqual({
    uri: 'file:///s/Statement.PDF',
    name: 'Statement.PDF',
    mime: 'application/pdf',
    size: 0,
  });
});

test('links without a file are ignored', () => {
  jest.spyOn(Linking, 'parse').mockReturnValueOnce({ queryParams: {} } as never);
  expect(shareAttachment('lifeagents://other')).toBeNull();
});
