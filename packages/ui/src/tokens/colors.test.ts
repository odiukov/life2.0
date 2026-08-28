import { darkColors } from './colors';

test('accent is amber', () => {
  expect(darkColors.accent).toBe('#c88600');
});
test('new semantic tokens exist', () => {
  expect(darkColors.fg4).toBeDefined();
  expect(darkColors.borderSoft).toBeDefined();
  expect(darkColors.accentInk).toBeDefined();
  expect(darkColors.info).toBeDefined();
});
