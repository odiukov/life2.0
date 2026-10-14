import { appLocale } from './locale';

const realDateTimeFormat = Intl.DateTimeFormat;

afterEach(() => {
  (Intl as { DateTimeFormat: typeof Intl.DateTimeFormat }).DateTimeFormat = realDateTimeFormat;
});

it.each([
  ['ru-RU', 'ru'],
  ['ru', 'ru'],
  ['en-US', 'en'],
  ['pt-PT', 'en'],
])('maps device locale %s to %s', (device, expected) => {
  (Intl as { DateTimeFormat: unknown }).DateTimeFormat = function () {
    return { resolvedOptions: () => ({ locale: device }) };
  } as unknown;
  expect(appLocale()).toBe(expected);
});
